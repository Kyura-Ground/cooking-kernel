#define _GNU_SOURCE
#include <errno.h>
#include <linux/bpf.h>
#include <linux/btf.h>
#include <poll.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Anonymous maps and BPF_PROG_TEST_RUN only; no pinning or attachment. */
#define I(c, d, s, o, v) ((struct bpf_insn) { \
	.code = (c), .dst_reg = (d), .src_reg = (s), .off = (o), .imm = (v) })
#define MOV(d, v) I(BPF_ALU64 | BPF_MOV | BPF_K, d, 0, 0, v)
#define COPY(d, s) I(BPF_ALU64 | BPF_MOV | BPF_X, d, s, 0, 0)
#define ADD(d, v) I(BPF_ALU64 | BPF_ADD | BPF_K, d, 0, 0, v)
#define CALL(v) I(BPF_JMP | BPF_CALL, 0, 0, 0, v)
#define EXIT() I(BPF_JMP | BPF_EXIT, 0, 0, 0, 0)
#define COUNT(a) (sizeof(a) / sizeof((a)[0]))

_Static_assert(BPF_MAP_TYPE_RINGBUF == 27, "ringbuf map ABI");
_Static_assert(BPF_FUNC_ringbuf_output == 130, "ringbuf helper ABI");
_Static_assert(BPF_FUNC_ringbuf_query == 134, "ringbuf helper ABI");
_Static_assert(BPF_CGROUP_INET_SOCK_RELEASE == 34, "socket release ABI");

static char verifier_log[65536];

static void require(int ok, const char *step)
{
	if (!ok) {
		fprintf(stderr, "FAIL: %s: errno=%d (%s)\n%s\n",
			step, errno, strerror(errno), verifier_log);
		exit(1);
	}
}

static int bpf(enum bpf_cmd cmd, union bpf_attr *attr)
{
	return syscall(__NR_bpf, cmd, attr, sizeof(*attr));
}

static int ring(unsigned int key, unsigned int size)
{
	return bpf(BPF_MAP_CREATE, &(union bpf_attr) {
		.map_type = BPF_MAP_TYPE_RINGBUF, .key_size = key, .max_entries = size,
	});
}

static int load(struct bpf_insn *code, size_t count, enum bpf_prog_type type,
		enum bpf_attach_type attach)
{
	verifier_log[0] = 0;
	return bpf(BPF_PROG_LOAD, &(union bpf_attr) {
		.prog_type = type, .expected_attach_type = attach,
		.insn_cnt = count, .insns = (uintptr_t)code,
		.license = (uintptr_t)"GPL", .log_level = 1,
		.log_buf = (uintptr_t)verifier_log, .log_size = sizeof(verifier_log),
	});
}

static void reject(struct bpf_insn *code, size_t count, const char *message)
{
	int fd = load(code, count, BPF_PROG_TYPE_SOCKET_FILTER, 0);
	int saved_errno = errno;

	if (fd >= 0)
		close(fd);
	errno = saved_errno;
	require(fd == -1 && (errno == EACCES || errno == EINVAL) &&
		strstr(verifier_log, message) != NULL, message);
	verifier_log[0] = 0;
}

static void run(struct bpf_insn *code, size_t count, unsigned int expected)
{
	unsigned char packet[64] = { 0 };
	int fd = load(code, count, BPF_PROG_TYPE_SOCKET_FILTER, 0);
	union bpf_attr attr = {
		.test = { .prog_fd = fd, .data_size_in = sizeof(packet),
			  .data_in = (uintptr_t)packet, .repeat = 1 },
	};

	require(fd >= 0, "load valid ringbuf helper program");
	require(bpf(BPF_PROG_TEST_RUN, &attr) == 0 && attr.test.retval == expected,
		"execute ringbuf helper program");
	close(fd);
	verifier_log[0] = 0;
}

static void cgroup_lookup(void)
{
	struct bpf_insn lookup[] = {
		I(BPF_ST | BPF_DW | BPF_MEM, 10, 0, -16, 0),
		I(BPF_ST | BPF_W | BPF_MEM, 10, 0, -8, 0),
		COPY(2, 10), ADD(2, -16), MOV(3, 12), MOV(4, -1), MOV(5, 0),
		CALL(BPF_FUNC_sk_lookup_tcp),
		I(BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 2, 0),
		COPY(1, 0), CALL(BPF_FUNC_sk_release), MOV(0, 1), EXIT(),
	};
	enum bpf_func_id helpers[] = {
		BPF_FUNC_sk_lookup_tcp, BPF_FUNC_sk_lookup_udp, BPF_FUNC_skc_lookup_tcp,
	};
	int fd, saved_errno;

	for (size_t i = 0; i < COUNT(helpers); i++) {
		lookup[7] = CALL(helpers[i]);
		fd = load(lookup, COUNT(lookup), BPF_PROG_TYPE_CGROUP_SKB,
			  BPF_CGROUP_INET_EGRESS);
		require(fd >= 0, "load cgroup skb socket lookup/release program");
		close(fd);
	}
	lookup[10] = MOV(0, 0);
	fd = load(lookup, COUNT(lookup), BPF_PROG_TYPE_CGROUP_SKB,
		  BPF_CGROUP_INET_EGRESS);
	saved_errno = errno;
	if (fd >= 0)
		close(fd);
	errno = saved_errno;
	require(fd == -1 && (errno == EACCES || errno == EINVAL) &&
		strstr(verifier_log, "Unreleased reference") != NULL,
		"socket lookup reference must be released");
	verifier_log[0] = 0;
	puts("PASS: cgroup skb TCP/UDP/common lookup, release and reference tracking (load only)");
}

static void cgroup_socket(void)
{
	struct {
		struct btf_header header;
		struct { struct btf_type type; uint32_t encoding; } integers[2];
		char names[9];
	} raw = {
		.header = { .magic = BTF_MAGIC, .version = BTF_VERSION,
			.hdr_len = sizeof(struct btf_header), .type_len = 32,
			.str_off = 32, .str_len = 9 },
		.integers = {
			{ .type = { .name_off = 1, .info = BTF_KIND_INT << 24, .size = 4 },
			  .encoding = 32 },
			{ .type = { .name_off = 5, .info = BTF_KIND_INT << 24, .size = 8 },
			  .encoding = 64 },
		},
		.names = "\0int\0u64",
	};
	int btf_fd = bpf(BPF_BTF_LOAD, &(union bpf_attr) {
		.btf = (uintptr_t)&raw, .btf_size = sizeof(raw.header) + 32 + 9,
	});
	int fd, prog;

	require(btf_fd >= 0, "socket storage BTF types");
	fd = bpf(BPF_MAP_CREATE, &(union bpf_attr) {
		.map_type = BPF_MAP_TYPE_SK_STORAGE, .key_size = 4, .value_size = 8,
		.map_flags = BPF_F_NO_PREALLOC, .btf_fd = btf_fd,
		.btf_key_type_id = 1, .btf_value_type_id = 2,
	});
	require(fd >= 0, "socket storage map");
	struct bpf_insn storage[] = {
		COPY(2, 1),
		I(BPF_LD | BPF_DW | BPF_IMM, 1, BPF_PSEUDO_MAP_FD, 0, fd), I(0, 0, 0, 0, 0),
		MOV(3, 0), MOV(4, BPF_SK_STORAGE_GET_F_CREATE), CALL(BPF_FUNC_sk_storage_get),
		I(BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 1, 0),
		I(BPF_ST | BPF_DW | BPF_MEM, 0, 0, 0, 0x12345678), MOV(0, 1), EXIT(),
	};
	struct bpf_insn cookie[] = { CALL(BPF_FUNC_get_socket_cookie), MOV(0, 1), EXIT() };
	enum bpf_attach_type hooks[] = { BPF_CGROUP_INET_SOCK_CREATE, BPF_CGROUP_INET_SOCK_RELEASE };

	for (size_t i = 0; i < COUNT(hooks); i++) {
		prog = load(storage, COUNT(storage), BPF_PROG_TYPE_CGROUP_SOCK, hooks[i]);
		require(prog >= 0, "load cgroup socket storage context program");
		close(prog);
		prog = load(cookie, COUNT(cookie), BPF_PROG_TYPE_CGROUP_SOCK, hooks[i]);
		require(prog >= 0, "load cgroup socket cookie program");
		close(prog);
	}
	struct bpf_insn skb_storage[] = {
		I(BPF_LDX | BPF_DW | BPF_MEM, 2, 1, offsetof(struct __sk_buff, sk), 0),
		I(BPF_JMP | BPF_JEQ | BPF_K, 2, 0, 5, 0),
		I(BPF_LD | BPF_DW | BPF_IMM, 1, BPF_PSEUDO_MAP_FD, 0, fd), I(0, 0, 0, 0, 0),
		MOV(3, 0), MOV(4, 0), CALL(BPF_FUNC_sk_storage_get), MOV(0, 1), EXIT(),
	};
	prog = load(skb_storage, COUNT(skb_storage), BPF_PROG_TYPE_CGROUP_SKB,
		    BPF_CGROUP_INET_INGRESS);
	require(prog >= 0, "load skb sock_common storage get program");
	close(prog);
	skb_storage[6] = CALL(BPF_FUNC_sk_storage_delete);
	prog = load(skb_storage, COUNT(skb_storage), BPF_PROG_TYPE_CGROUP_SKB,
		    BPF_CGROUP_INET_INGRESS);
	require(prog >= 0, "load skb sock_common storage delete program");
	close(prog);
	close(fd);
	close(btf_fd);
	verifier_log[0] = 0;
	puts("PASS: cgroup socket create/release ABI, storage context and cookie helpers (load only)");
	puts("PASS: skb sock_common storage get/delete helper programs (load only)");
}

int main(void)
{
	const unsigned int size = 32768;
	long page = sysconf(_SC_PAGESIZE);
	volatile uint64_t *consumer, *producer;
	unsigned char *mapping, *data, *bad;
	int fd, control, ret;
	struct pollfd pollfd;
	struct rlimit limit = { RLIM_INFINITY, RLIM_INFINITY };

	require(setrlimit(RLIMIT_MEMLOCK, &limit) == 0, "probe process memlock limit");
	require(page == 4096, "X00TD 4KiB page size");
	control = bpf(BPF_MAP_CREATE, &(union bpf_attr) {
		.map_type = BPF_MAP_TYPE_ARRAY, .key_size = 4,
		.value_size = 8, .max_entries = 1,
	});
	require(control >= 0, "plain BPF map control");
	fd = ring(0, size);
	require(fd >= 0, "packet_trace_ringbuf BPF_MAP_CREATE");
	ret = ring(4, size);
	if (ret >= 0)
		close(ret);
	require(ret == -1 && errno == EINVAL, "ringbuf rejects nonzero key size");
	ret = ring(0, 3 * page);
	if (ret >= 0)
		close(ret);
	require(ret == -1 && errno == EINVAL, "ringbuf requires power-of-two size");
	consumer = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	require(consumer != MAP_FAILED, "writable consumer mapping");
	mapping = mmap(NULL, page + 2 * size, PROT_READ, MAP_SHARED, fd, page);
	require(mapping != MAP_FAILED, "read-only producer and double data mapping");
	producer = (volatile uint64_t *)mapping;
	data = mapping + page;
	require(*consumer == 0 && *producer == 0, "initial empty ringbuf positions");
	ret = mprotect(mapping, page, PROT_READ | PROT_WRITE);
	require(ret == -1 && errno == EACCES, "producer mapping cannot gain write permission");
	bad = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_SHARED, fd, page);
	require(bad == MAP_FAILED && errno == EPERM, "producer page rejects writable mmap");
	bad = mmap(NULL, 2 * page, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	require(bad == MAP_FAILED && errno == EPERM, "writable mapping cannot include producer");
	bad = mmap(NULL, page, PROT_READ, MAP_SHARED, fd, 2 * page + 2 * size);
	require(bad == MAP_FAILED && errno == EINVAL, "mapping past ringbuf rejected");
	pollfd = (struct pollfd) { .fd = fd, .events = POLLIN };
	require(poll(&pollfd, 1, 0) == 0, "empty ringbuf poll");

	struct bpf_insn reserve[] = {
		I(BPF_LD | BPF_DW | BPF_IMM, 1, BPF_PSEUDO_MAP_FD, 0, fd), I(0, 0, 0, 0, 0),
		MOV(2, 8), MOV(3, 0), CALL(BPF_FUNC_ringbuf_reserve),
		I(BPF_JMP | BPF_JEQ | BPF_K, 0, 0, 5, 0),
		I(BPF_ST | BPF_DW | BPF_MEM, 0, 0, 0, 0x12345678),
		I(BPF_STX | BPF_DW | BPF_MEM, 10, 0, -8, 0),
		I(BPF_LDX | BPF_DW | BPF_MEM, 1, 10, -8, 0),
		MOV(2, BPF_RB_FORCE_WAKEUP), CALL(BPF_FUNC_ringbuf_submit), MOV(0, 0), EXIT(),
	};
	run(reserve, COUNT(reserve), 0);
	require(poll(&pollfd, 1, 1000) == 1 && (pollfd.revents & POLLIN), "committed record poll");
	require(*producer == 16 && *(uint32_t *)data == 8 &&
		*(uint64_t *)(data + 8) == 0x12345678, "reserve, spill, write and submit record");
	require(!memcmp(data, data + size, 16), "double-mapped data aliases");
	/* All producers run synchronously via TEST_RUN; no concurrent counter writes. */
	*consumer = *producer;
	require(poll(&pollfd, 1, 0) == 0, "consumed ringbuf poll");
	reserve[10] = CALL(BPF_FUNC_ringbuf_discard);
	run(reserve, COUNT(reserve), 0);
	require(*producer == 32 && (*(uint32_t *)(data + 16) & BPF_RINGBUF_DISCARD_BIT),
		"discard marks reserved record");
	*consumer = *producer;
	reserve[10] = CALL(BPF_FUNC_ringbuf_submit);

	struct bpf_insn query[] = {
		I(BPF_LD | BPF_DW | BPF_IMM, 1, BPF_PSEUDO_MAP_FD, 0, fd), I(0, 0, 0, 0, 0),
		MOV(2, BPF_RB_RING_SIZE), CALL(BPF_FUNC_ringbuf_query), EXIT(),
	};
	run(query, COUNT(query), size);
	query[0].imm = control;
	reject(query, COUNT(query), "cannot pass map_type");

	struct bpf_insn output[] = {
		I(BPF_ST | BPF_DW | BPF_MEM, 10, 0, -8, 0x23456789),
		I(BPF_LD | BPF_DW | BPF_IMM, 1, BPF_PSEUDO_MAP_FD, 0, fd), I(0, 0, 0, 0, 0),
		COPY(2, 10), ADD(2, -8), MOV(3, 8), MOV(4, 0),
		CALL(BPF_FUNC_ringbuf_output), EXIT(),
	};
	run(output, COUNT(output), 0);
	require(*producer == 48 && *(uint64_t *)(data + 40) == 0x23456789,
		"output copies record payload");
	*consumer = *producer;

	reserve[6].off = 8;
	reject(reserve, COUNT(reserve), "invalid access to memory");
	reserve[6].off = 0;
	reserve[10] = MOV(0, 0);
	reject(reserve, COUNT(reserve), "Unreleased reference");
	reserve[10] = CALL(BPF_FUNC_ringbuf_submit);

	struct bpf_insn shifted[COUNT(reserve) + 1];
	memcpy(shifted, reserve, 9 * sizeof(*reserve));
	shifted[5].off++;
	shifted[9] = ADD(1, 8);
	memcpy(shifted + 10, reserve + 9, (COUNT(reserve) - 9) * sizeof(*reserve));
	reject(shifted, COUNT(shifted), "must have zero offset");
	memcpy(shifted, reserve, 5 * sizeof(*reserve));
	shifted[5] = ADD(0, 1);
	memcpy(shifted + 6, reserve + 5, (COUNT(reserve) - 5) * sizeof(*reserve));
	reject(shifted, COUNT(shifted), "pointer arithmetic on mem_or_null prohibited");

	require(munmap((void *)consumer, page) == 0, "consumer mapping cleanup");
	require(munmap(mapping, page + 2 * size) == 0, "producer mapping cleanup");
	close(fd);
	close(control);
	puts("PASS: BPF ringbuf map, mmap, poll, five helpers, bounds and reference tracking");
	cgroup_socket();
	cgroup_lookup();
	return 0;
}
