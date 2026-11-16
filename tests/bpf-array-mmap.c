#define _GNU_SOURCE
#include <errno.h>
#include <linux/bpf.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <unistd.h>

/* Exercise anonymous maps only; nothing is pinned or attached to networking. */
static void require(int ok, const char *step)
{
	if (!ok) {
		fprintf(stderr, "FAIL: %s: errno=%d (%s)\n",
			step, errno, strerror(errno));
		exit(1);
	}
}

static int bpf(enum bpf_cmd cmd, union bpf_attr *attr)
{
	return syscall(__NR_bpf, cmd, attr, sizeof(*attr));
}

static int array(unsigned int flags, unsigned int size, unsigned int entries)
{
	union bpf_attr attr = {
		.map_type = BPF_MAP_TYPE_ARRAY,
		.key_size = sizeof(uint32_t),
		.value_size = size,
		.max_entries = entries,
		.map_flags = flags,
	};

	return bpf(BPF_MAP_CREATE, &attr);
}

int main(void)
{
	long page_size = sysconf(_SC_PAGESIZE);
	size_t page, size;
	size_t offsets[3];
	unsigned int entries;
	uint32_t key = 0, next = UINT32_MAX;
	uint64_t in = 0x12345678, out = 0;
	unsigned char *rw, *ro, *part, *buffer;
	int fd, ret;

	require(page_size > 0 && (unsigned long)page_size <= UINT32_MAX / 2, "page size");
	page = page_size;
	size = 2 * page;
	entries = size / sizeof(uint64_t);
	offsets[0] = 0;
	offsets[1] = page;
	offsets[2] = size - sizeof(uint64_t);
	buffer = calloc(1, size);
	require(buffer != NULL, "value buffer");
	fd = array(0, sizeof(uint64_t), entries);
	require(fd >= 0, "plain BPF_MAP_CREATE control");
	close(fd);
	printf("Probe: ARRAY key=4 value=8 entries=%u flags=0x%x\n",
		entries, BPF_F_MMAPABLE);
	fd = array(BPF_F_MMAPABLE, sizeof(uint64_t), entries);
	require(fd >= 0, "blocked_ports_map shape BPF_MAP_CREATE");
	rw = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	require(rw != MAP_FAILED, "shared read/write mmap");
	require(!memcmp(rw, buffer, size), "zero-filled map memory");
	rw[0] = 0xa5;
	rw[page] = 0x5a;
	rw[size - 1] = 0x7f;
	for (unsigned int i = 0; i < 3; i++) {
		key = offsets[i] / sizeof(uint64_t);
		ret = bpf(BPF_MAP_LOOKUP_ELEM, &(union bpf_attr) {
			.map_fd = fd, .key = (uintptr_t)&key,
			.value = (uintptr_t)(buffer + offsets[i]),
		});
		require(ret == 0, "lookup of mapped array entry");
	}
	require(buffer[0] == 0xa5 && buffer[page] == 0x5a &&
		buffer[size - 1] == 0x7f, "mapped writes visible to map lookup");
	key = 0;
	buffer[1] = 0x42;
	ret = bpf(BPF_MAP_UPDATE_ELEM, &(union bpf_attr) {
		.map_fd = fd, .key = (uintptr_t)&key, .value = (uintptr_t)buffer,
	});
	require(ret == 0 && rw[1] == 0x42, "map update visible to mmap");
	ret = bpf(BPF_MAP_GET_NEXT_KEY, &(union bpf_attr) {
		.map_fd = fd, .next_key = (uintptr_t)&next,
	});
	require(ret == 0 && next == 0, "read-only key iteration");
	ret = bpf(BPF_MAP_DELETE_ELEM, &(union bpf_attr) {
		.map_fd = fd, .key = (uintptr_t)&key,
	});
	require(ret == -1 && errno == EINVAL, "array delete rejection");
	part = mmap(NULL, page, PROT_READ, MAP_SHARED, fd, page);
	require(part != MAP_FAILED && part[0] == 0x5a, "nonzero page offset");
	require(munmap(part, page) == 0, "partial mapping cleanup");
	part = mmap(NULL, page, PROT_READ | PROT_WRITE, MAP_SHARED, fd, size);
	require(part == MAP_FAILED && errno == EINVAL, "out-of-range mapping rejection");
	ret = bpf(BPF_MAP_FREEZE, &(union bpf_attr) { .map_fd = fd });
	require(ret == -1 && errno == EBUSY, "freeze blocked by writable mapping");
	require(munmap(rw, size) == 0, "writable mapping cleanup");
	ro = mmap(NULL, size, PROT_READ, MAP_SHARED, fd, 0);
	require(ro != MAP_FAILED, "read-only mmap");
	ret = mprotect(ro, size, PROT_READ | PROT_WRITE);
	require(ret == -1 && errno == EACCES, "read-only mapping cannot gain write permission");
	ret = bpf(BPF_MAP_FREEZE, &(union bpf_attr) { .map_fd = fd });
	require(ret == 0, "freeze after completed writes and with read-only mapping");
	part = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	require(part == MAP_FAILED && errno == EPERM, "frozen map rejects writable mmap");
	ret = bpf(BPF_MAP_UPDATE_ELEM, &(union bpf_attr) {
		.map_fd = fd, .key = (uintptr_t)&key, .value = (uintptr_t)buffer,
	});
	require(ret == -1 && errno == EPERM, "frozen map rejects syscall updates");
	require(munmap(ro, size) == 0, "read-only mapping cleanup");
	close(fd);

	fd = array(BPF_F_MMAPABLE | BPF_F_RDONLY_PROG, sizeof(uint64_t), entries);
	require(fd >= 0, "program-read-only BPF_MAP_CREATE");
	part = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	require(part == MAP_FAILED && errno == EACCES, "program-read-only map rejects writable mmap");
	ro = mmap(NULL, size, PROT_READ, MAP_SHARED, fd, 0);
	require(ro != MAP_FAILED, "program-read-only map allows read-only mmap");
	ret = bpf(BPF_MAP_FREEZE, &(union bpf_attr) { .map_fd = fd });
	require(ret == 0, "denied writable mapping leaves no active writer");
	require(munmap(ro, size) == 0, "program-read-only mapping cleanup");
	close(fd);

	fd = bpf(BPF_MAP_CREATE, &(union bpf_attr) {
		.map_type = BPF_MAP_TYPE_QUEUE, .value_size = sizeof(in), .max_entries = 1,
	});
	require(fd >= 0, "queue BPF_MAP_CREATE");
	ret = bpf(BPF_MAP_UPDATE_ELEM, &(union bpf_attr) {
		.map_fd = fd, .value = (uintptr_t)&in,
	});
	require(ret == 0, "queue push");
	ret = bpf(BPF_MAP_LOOKUP_AND_DELETE_ELEM, &(union bpf_attr) {
		.map_fd = fd, .value = (uintptr_t)&out,
	});
	require(ret == 0 && out == in, "queue lookup and delete");
	ret = bpf(BPF_MAP_FREEZE, &(union bpf_attr) { .map_fd = fd });
	require(ret == 0, "queue write counters released after lookup and delete");
	close(fd);
	free(buffer);
	puts("PASS: BPF array mmap, offsets, permissions, freeze and writer counters");
	return 0;
}
