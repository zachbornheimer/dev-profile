package devprofile_test

import (
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const (
	personalRepo = "/Users/zbornheimer/Developer/Personal/attention-mail"
	companyRepo  = "/Users/zbornheimer/Developer/Software-Automation-Holdings/dev-config"
	overlayPath  = "/Users/zbornheimer/Developer/Personal/mise.toml"
)

func lookPath(t *testing.T, name string) string {
	t.Helper()
	p, err := exec.LookPath(name)
	if err != nil {
		t.Fatalf("look path %s: %v", name, err)
	}
	return p
}

func run(t *testing.T, dir, bin string, timeout time.Duration, args ...string) (string, error) {
	t.Helper()
	cmd := exec.Command(bin, args...)
	cmd.Dir = dir
	cmd.Env = os.Environ()
	var b strings.Builder
	cmd.Stdout = &b
	cmd.Stderr = &b
	done := make(chan error, 1)
	go func() { done <- cmd.Run() }()
	select {
	case err := <-done:
		return b.String(), err
	case <-time.After(timeout):
		_ = cmd.Process.Kill()
		return b.String(), os.ErrDeadlineExceeded
	}
}

func TestPersonalDirectorySelectsPersonalOverlay(t *testing.T) {
	mise := lookPath(t, "mise")
	here, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for _, dir := range []string{personalRepo, here} {
		t.Run(filepath.Base(dir), func(t *testing.T) {
			ls, err := run(t, dir, mise, 30*time.Second, "config", "ls")
			if err != nil {
				t.Fatalf("mise config ls in %s: %v\n%s", dir, err, ls)
			}
			if !strings.Contains(ls, overlayPath) && !strings.Contains(ls, "Developer/Personal/mise.toml") {
				t.Fatalf("personal overlay missing from mise config ls in %s\n%s", dir, ls)
			}
			env, err := run(t, dir, mise, 30*time.Second, "env")
			if err != nil {
				t.Fatalf("mise env in %s: %v\n%s", dir, err, env)
			}
			if !strings.Contains(env, "DEV_PROFILE=personal") {
				t.Fatalf("DEV_PROFILE=personal missing from mise env in %s\n%s", dir, env)
			}
		})
	}
}

func TestCompanyDirectoryDoesNotApplyPersonalOverlay(t *testing.T) {
	mise := lookPath(t, "mise")
	ls, err := run(t, companyRepo, mise, 30*time.Second, "config", "ls")
	if err != nil {
		t.Fatalf("mise config ls in company repo: %v\n%s", err, ls)
	}
	if strings.Contains(ls, "Developer/Personal/mise.toml") {
		t.Fatalf("personal overlay leaked into company mise config ls\n%s", ls)
	}
	env, err := run(t, companyRepo, mise, 30*time.Second, "env")
	if err != nil {
		t.Fatalf("mise env in company repo: %v\n%s", err, env)
	}
	if strings.Contains(env, "DEV_PROFILE=personal") {
		t.Fatalf("DEV_PROFILE=personal leaked into company mise env\n%s", env)
	}
}

func TestDogfoodMiseRunFmt(t *testing.T) {
	mise := lookPath(t, "mise")
	out, err := run(t, personalRepo, mise, 3*time.Minute, "run", "fmt")
	if err != nil {
		t.Fatalf("mise run fmt: %v\n%s", err, out)
	}
	if strings.TrimSpace(out) == "" {
		t.Fatal("mise run fmt produced empty output")
	}
}

func TestDogfoodMiseRunTest(t *testing.T) {
	mise := lookPath(t, "mise")
	out, err := run(t, personalRepo, mise, 3*time.Minute, "run", "test")
	if err != nil {
		t.Fatalf("mise run test: %v\n%s", err, out)
	}
	if strings.TrimSpace(out) == "" {
		t.Fatal("mise run test produced empty output")
	}
}

func TestInstalledOverlayMatchesSource(t *testing.T) {
	src, err := os.ReadFile("profiles/personal.toml")
	if err != nil {
		t.Fatal(err)
	}
	dst, err := os.ReadFile(overlayPath)
	if err != nil {
		t.Fatal(err)
	}
	if string(src) != string(dst) {
		t.Fatalf("live overlay %s does not match profiles/personal.toml", overlayPath)
	}
}

func TestZQStillInstalled(t *testing.T) {
	first := lookPath(t, "zq")
	second := lookPath(t, "zq")
	if first != second {
		t.Fatalf("zq path changed between lookups: %s vs %s", first, second)
	}
	v1, err := run(t, personalRepo, first, 30*time.Second, "version")
	if err != nil {
		t.Fatalf("zq version (1): %v\n%s", err, v1)
	}
	v2, err := run(t, personalRepo, second, 30*time.Second, "version")
	if err != nil {
		t.Fatalf("zq version (2): %v\n%s", err, v2)
	}
	if strings.TrimSpace(v1) == "" || strings.TrimSpace(v1) != strings.TrimSpace(v2) {
		t.Fatalf("zq version mismatch: %q vs %q", v1, v2)
	}
}
