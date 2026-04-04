CPP = g++
GCC_TARGET := $(shell gcc -dumpmachine)
MARCH = 
ifeq (,$(findstring darwin,$(GCC_TARGET)))
    MARCH += -march=native -fopenmp
endif
#CCFLAGS = -Wall -g -std=c++14 -D_GLIBCXX_PARALLEL -march=native -funroll-loops -fopenmp
CCFLAGS = -Wall -g -std=c++14 -funroll-loops $(MARCH)
INCLUDES = ./include
LFLAGS = 
DEBUG = 0
LIBS = -lm
BIN = bin
SRC = src
SRCS := $(wildcard $(SRC)/*.cpp)
OBJS := $(patsubst ${SRC}%.cpp,${BIN}%.o,$(SRCS))
DEPS := $(OBJS:.o=.d)
DEPFLAGS = -MMD -MP

MAIN = hanan_router

OPTFLAGS = -O3 -ffast-math
#OPTFLAGS = 
ifeq ($(DEBUG), 1)
OPTFLAGS = 
endif
.PHONY: depend clean

$(MAIN): $(OBJS) 
	$(CPP) $(CCFLAGS) $(OPTFLAGS) -I$(INCLUDES) -o $(MAIN) $(OBJS) $(LFLAGS) $(LIBS)

$(BIN)/%.o: $(SRC)/%.cpp 
	@mkdir -p $(BIN)
	$(CPP) $(CCFLAGS) $(OPTFLAGS) -I$(INCLUDES) -DDEBUG=$(DEBUG) $(DEPFLAGS) -c $< -o $@

clean:
	rm -rf $(MAIN) $(BIN)/*.o $(BIN)/*.d

-include $(DEPS)

