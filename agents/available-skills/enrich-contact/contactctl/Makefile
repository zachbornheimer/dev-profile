BINDIR := bin
BIN := $(BINDIR)/contactctl

.PHONY: build clean fmt

build:
	swift build -c release
	@mkdir -p $(BINDIR)
	@cp -f .build/release/contactctl $(BIN)
	@echo "built $(BIN)"

fmt:
	@command -v swift-format >/dev/null 2>&1 && swift-format -i -r Sources || echo "swift-format not installed; skipping"

clean:
	swift package clean
	rm -rf $(BINDIR) .build
