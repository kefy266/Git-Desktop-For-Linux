# Git Desktop For Linux — native C / GTK4 / libadwaita edition
#
#   make            build ./build/git-desktop
#   make run        build and start it on this repository
#   make test       run the unit tests (git layer, diff parser)
#   make install    install to ~/.local (binary, .desktop entry, icon)

APP      := git-desktop
APP_ID   := com.github.kefy266.GitDesktopLinux
PREFIX   ?= $(HOME)/.local
BUILD    := build

PKGS     := gtk4 libadwaita-1 gtksourceview-5 libgit2 libsecret-1 json-glib-1.0 libsoup-3.0
TEST_PKGS := gio-2.0 libgit2

CC       ?= cc
CFLAGS   ?= -O2 -g
# `override`: keep these even when CFLAGS is given on the command line (e.g. sanitizers)
override CFLAGS += -std=gnu17 -Wall -Wextra -Wno-unused-parameter -Wno-missing-field-initializers \
            -DAPP_ID=\"$(APP_ID)\" -MMD -MP
APP_CFLAGS  := $(shell pkg-config --cflags $(PKGS))
APP_LIBS    := $(shell pkg-config --libs $(PKGS)) -lm
TEST_CFLAGS := $(shell pkg-config --cflags $(TEST_PKGS))
TEST_LIBS   := $(shell pkg-config --libs $(TEST_PKGS))

SRC := $(wildcard src/*.c)
OBJ := $(SRC:src/%.c=$(BUILD)/%.o)

all: $(BUILD)/$(APP)

$(BUILD)/$(APP): $(OBJ)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $^ $(APP_LIBS)

$(BUILD)/%.o: src/%.c | $(BUILD)
	$(CC) $(CFLAGS) $(APP_CFLAGS) -c -o $@ $<

$(BUILD):
	mkdir -p $(BUILD)

# Tests only need the GTK-free parts
$(BUILD)/test-git: tests/test_git.c src/git.c src/net.c src/diffparse.c src/util.c | $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) $(TEST_CFLAGS) -Isrc -o $@ $^ $(TEST_LIBS)

test: $(BUILD)/test-git
	$(BUILD)/test-git

run: $(BUILD)/$(APP)
	$(BUILD)/$(APP) "$(abspath ..)"

install: $(BUILD)/$(APP)
	install -Dm755 $(BUILD)/$(APP) $(PREFIX)/bin/$(APP)
	install -Dm644 data/$(APP_ID).desktop $(PREFIX)/share/applications/$(APP_ID).desktop
	install -Dm644 data/$(APP_ID).svg $(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg
	-update-desktop-database $(PREFIX)/share/applications 2>/dev/null

uninstall:
	rm -f $(PREFIX)/bin/$(APP) $(PREFIX)/share/applications/$(APP_ID).desktop \
	      $(PREFIX)/share/icons/hicolor/scalable/apps/$(APP_ID).svg

clean:
	rm -rf $(BUILD)

.PHONY: all test run install uninstall clean
-include $(OBJ:.o=.d)
