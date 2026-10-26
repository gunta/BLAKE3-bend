//go:build cgo && !(darwin && amd64) && !(darwin && arm64)

// The engine for a platform with no prebuilt engine_<os>_<arch>.syso:
// compiled by cgo, which will not pass the vectorizer's -mllvm flags, so
// its 8-lane compression runs scalar. Slower; still on every core.
#define BEND_EMBED 1
#define main b3e_bend_main
#include "csrc/engine.c"
