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
OBJ := $(shell for i in *.c; do echo $(OUTDIR)/$${i%.c}.o; done)

# Pattern rules
$(OUTDIR)/%.o : %.c
	gcc -fpermissive -Dlinux=1 -fPIC -c  -v  $(CCARGS) -o "$(OUTDIR)/$(*F).o" "$<"

# Build rules
all: $(OUTDIR)/$(NAME).a $(OUTDIR)/$(NAME).so $(OUTDIR)/demo

$(OUTDIR)/$(NAME).a: $(OUTDIR)  $(OBJ)
	ar -rs  "$@" $(OBJ)

$(OUTDIR)/$(NAME).so: $(OUTDIR)  $(OBJ)
	gcc -shared -Wl,-soname,$(NAME).so -o "$@" $(OBJ)

$(OUTDIR)/demo: $(OUTDIR) $(OUTDIR)/demo.o $(OUTDIR)/$(NAME).a
	gcc -o "$@" "$(OUTDIR)/demo.o" $(OUTDIR)/$(NAME).a -lpthread -lm -ldl

$(OUTDIR):
	mkdir -p "$(OUTDIR)"

# Rebuild this project
rebuild: cleanall all

# Clean this project
clean:
	rm -rf $(OUTDIR)

# Clean this project and all dependencies
cleanall: clean
