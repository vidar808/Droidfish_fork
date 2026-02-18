LOCAL_PATH := $(call my-dir)

include $(CLEAR_VARS)

LOCAL_MODULE := rodent4

LOCAL_SRC_FILES := \
	attacks.cpp bitboard.cpp book.cpp data.cpp edata.cpp \
	eval.cpp eval_draw.cpp eval_patterns.cpp eval_pawn.cpp \
	gen.cpp init.cpp legal.cpp magicmoves.cpp main.cpp mask.cpp \
	movedo.cpp moveundo.cpp next.cpp params.cpp quiesce.cpp \
	recognize.cpp search.cpp setboard.cpp swap.cpp taunt.cpp \
	trans.cpp tuning.cpp uci.cpp uci_options.cpp util.cpp

LOCAL_CFLAGS := -std=c++14 -O3 -fno-exceptions -fPIE -s -flto=thin \
	-DNO_MM_POPCNT

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
