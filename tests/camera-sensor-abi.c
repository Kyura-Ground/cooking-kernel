/* Match the 32-bit X00TD sensor probe payload captured from the vendor HAL. */
#include <stddef.h>
#include <stdint.h>
#include <media/msm_camsensor_sdk.h>

_Static_assert(sizeof(void *) == 4, "compile this ABI check for ARM32");
_Static_assert(sizeof(struct msm_sensor_id_info_t) == 6,
	       "vendor sensor ID has no register-write extension");
_Static_assert(offsetof(struct msm_camera_sensor_slave_info,
		       power_setting_array.power_setting) == 856,
	       "vendor power-up pointer offset");
_Static_assert(offsetof(struct msm_camera_sensor_slave_info,
		       power_setting_array.size) == 860,
	       "vendor power-up count offset (8 in the captured probe)");
_Static_assert(offsetof(struct msm_camera_sensor_slave_info,
		       power_setting_array.power_down_setting) == 1536,
	       "vendor power-down pointer offset");
_Static_assert(offsetof(struct msm_camera_sensor_slave_info,
		       power_setting_array.size_down) == 1540,
	       "vendor power-down count offset");
_Static_assert(sizeof(struct msm_camera_sensor_slave_info) == 1568,
	       "vendor sensor probe payload size");
