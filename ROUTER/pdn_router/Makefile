CXX = g++
ROUTER_DIR = ../hanan_router
BIN = bin

GCC_TARGET := $(shell gcc -dumpmachine)
MARCH =
ifeq (,$(findstring darwin,$(GCC_TARGET)))
    MARCH += -march=native -fopenmp
endif

CXXFLAGS = -Wall -g -std=c++14 -funroll-loops $(MARCH) -O3 -ffast-math
INCLUDES = -I$(ROUTER_DIR)/include -I$(ROUTER_DIR)/src
DEPFLAGS = -MMD -MP

COMMON_SRCS := $(filter-out $(ROUTER_DIR)/src/Net.cpp,$(wildcard $(ROUTER_DIR)/src/*.cpp))
COMMON_OBJS := $(patsubst $(ROUTER_DIR)/src/%.cpp,$(BIN)/%.o,$(COMMON_SRCS))
OBJS := $(COMMON_OBJS) $(BIN)/Net.o
DEPS := $(OBJS:.o=.d)
MAIN = pdn_router

.PHONY: all clean

all: $(MAIN)

$(MAIN): $(OBJS)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -o $@ $(OBJS) -lm

$(BIN)/Net.o: src/Net.cpp
	@mkdir -p $(BIN)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -DDEBUG=0 $(DEPFLAGS) -c $< -o $@

$(BIN)/%.o: $(ROUTER_DIR)/src/%.cpp
	@mkdir -p $(BIN)
	$(CXX) $(CXXFLAGS) $(INCLUDES) -DDEBUG=0 $(DEPFLAGS) -c $< -o $@

clean:
	rm -rf $(MAIN) $(BIN)

-include $(DEPS)
