# Designed to be build on the Raspberry Pi using gcc

ifndef CFG
CFG=Debug
endif

ifeq "$(CFG)" "Debug"
OUTDIR=Debug
CCARGS=-g -DDEBUG=1
else
OUTDIR=Release
CCARGS=-O2
endif

NAME=libleptonDriver
OBJ := $(patsubst %.c,$(OUTDIR)/%.o,$(wildcard *.c))

# Pattern rules: use $@ and $< so targets and prerequisites line up correctly.
# Make sure the OUTDIR exists as an order-only prerequisite so changing the dir
# timestamp doesn't force rebuilds of downstream targets.
$(OUTDIR)/%.o : %.c | $(OUTDIR)
	gcc -Dlinux=1 -fPIC -c $(CCARGS) -o $@ $<

# Build rules
all: $(OUTDIR)/$(NAME).a $(OUTDIR)/$(NAME).so $(OUTDIR)/capture

$(OUTDIR)/$(NAME).a: $(OBJ)
	ar -rs  "$@" $(OBJ)

$(OUTDIR)/$(NAME).so: $(OBJ)
	gcc -shared -Wl,-soname,$(NAME).so -o "$@" $(OBJ)

$(OUTDIR)/capture: $(OUTDIR)/capture.o $(OUTDIR)/$(NAME).a
	gcc -o "$@" "$(OUTDIR)/capture.o" $(OUTDIR)/$(NAME).a -lpthread -lm -ldl

$(OUTDIR):
	mkdir -p "$(OUTDIR)"

# Rebuild this project
rebuild: cleanall all

# Clean this project
clean:
	rm -rf $(OUTDIR)

# Clean this project and all dependencies
cleanall: clean

