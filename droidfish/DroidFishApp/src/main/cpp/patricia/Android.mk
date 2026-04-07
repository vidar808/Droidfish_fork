LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)

LOCAL_MODULE := patricia

LOCAL_SRC_FILES := \
	src/patricia.cpp \
	src/fathom/src/tbprobe.c

LOCAL_CFLAGS := -std=c++20 -O3 -fPIE -s -flto=thin
LOCAL_CONLYFLAGS := -std=c11
LOCAL_CFLAGS += -I$(LOCAL_PATH)/src

ifeq ($(TARGET_ARCH_ABI),arm64-v8a)
  LOCAL_CFLAGS += -DIS_64BIT
endif
ifeq ($(TARGET_ARCH_ABI),armeabi-v7a)
  LOCAL_ARM_NEON := true
  LOCAL_CFLAGS += -mthumb -march=armv7-a -mfloat-abi=softfp -mfpu=neon
endif
ifeq ($(TARGET_ARCH_ABI),x86_64)
  LOCAL_CFLAGS += -DIS_64BIT
endif

LOCAL_LDFLAGS += -fPIE -s -flto=thin

include $(BUILD_EXECUTABLE)
