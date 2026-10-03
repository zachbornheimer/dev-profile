package devprofile_test

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const (
	personalRepo    = "/Users/zbornheimer/Developer/Personal/attention-mail"
	companyRepo     = "/Users/zbornheimer/Developer/Software-Automation-Holdings/dev-config"
	overlayPath     = "/Users/zbornheimer/Developer/Personal/mise.toml"
	dprintConfig    = "/Users/zbornheimer/Developer/Personal/dprint.jsonc"
	worktrunkConfig = "/Users/zbornheimer/.config/worktrunk/config.toml"
	worktreePath    = `{{ repo_path }}/../.worktrees/{{ repo }}-{{ branch | sanitize }}`
)

func lookPath(t *testing.T, name string) string {
	t.Helper()
	p, err := exec.LookPath(name)
	if err != nil {
		t.Fatalf("look path %s: %v", name, err)
	}
	return p
}

func envWithout(name string) []string {
	prefix := name + "="
	env := os.Environ()
	out := make([]string, 0, len(env))
	for _, e := range env {
		if strings.HasPrefix(e, prefix) {
			continue
		}
		out = append(out, e)
	}
	return out
}

func run(t *testing.T, dir, bin string, timeout time.Duration, args ...string) (string, error) {
	t.Helper()
	return runEnv(t, dir, bin, os.Environ(), timeout, args...)
}

func runEnv(t *testing.T, dir, bin string, env []string, timeout time.Duration, args ...string) (string, error) {
	t.Helper()
	cmd := exec.Command(bin, args...)
	cmd.Dir = dir
	cmd.Env = env
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

func TestParentFmtTaskRunsInInvokingRepo(t *testing.T) {
	src, err := os.ReadFile("profiles/personal.toml")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(src), `dir = "{{cwd}}"`) {
		t.Fatal(`profiles/personal.toml missing dir = "{{cwd}}"`)
	}

	const agentmuxDir = "/Users/zbornheimer/Developer/Personal/agentmux"
	miseToml, err := os.ReadFile(filepath.Join(agentmuxDir, ".mise.toml"))
	if err != nil {
		t.Fatalf("read agentmux .mise.toml: %v", err)
	}
	if bytes.Contains(miseToml, []byte("[tasks.fmt]")) {
		t.Skip("agentmux .mise.toml has [tasks.fmt]; parent cwd test does not apply")
	}

	mise := lookPath(t, "mise")
	out, err := run(t, agentmuxDir, mise, 30*time.Second, "tasks", "--json")
	if err != nil {
		t.Fatalf("mise tasks --json in agentmux: %v\n%s", err, out)
	}

	var tasks []struct {
		Name string `json:"name"`
		Dir  string `json:"dir"`
	}
	if err := json.Unmarshal([]byte(out), &tasks); err != nil {
		t.Fatalf("decode mise tasks --json: %v\n%s", err, out)
	}
	for _, task := range tasks {
		if task.Name != "fmt" {
			continue
		}
		if task.Dir != agentmuxDir {
			t.Fatalf("fmt task dir = %q, want %q", task.Dir, agentmuxDir)
		}
		return
	}
	t.Fatal("mise tasks --json in agentmux missing task named fmt")
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

func TestInstallStrictDoesNotLeak(t *testing.T) {
	mise := lookPath(t, "mise")
	childEnv := envWithout("AGENTMUX_INSTALL_STRICT")
	for _, dir := range []string{companyRepo, personalRepo} {
		t.Run(filepath.Base(dir), func(t *testing.T) {
			out, err := runEnv(t, dir, mise, childEnv, 30*time.Second, "env")
			if err != nil {
				t.Fatalf("mise env in %s: %v\n%s", dir, err, out)
			}
			if strings.Contains(out, "AGENTMUX_INSTALL_STRICT") {
				t.Fatalf("AGENTMUX_INSTALL_STRICT leaked from mise env in %s\n%s", dir, out)
			}
		})
	}
	t.Run("agentmux-install-main", func(t *testing.T) {
		const agentmuxDir = "/Users/zbornheimer/Developer/Personal/.worktrees/agentmux-install-main"
		if _, err := os.Stat(filepath.Join(agentmuxDir, ".mise.toml")); err != nil {
			t.Skip("agentmux-install-main worktree or .mise.toml absent")
		}
		out, err := runEnv(t, agentmuxDir, mise, childEnv, 30*time.Second, "env")
		if err != nil {
			t.Fatalf("mise env in agentmux-install-main: %v\n%s", err, out)
		}
		if !strings.Contains(out, "AGENTMUX_INSTALL_STRICT") {
			t.Fatalf("AGENTMUX_INSTALL_STRICT missing from mise env in agentmux-install-main\n%s", out)
		}
	})
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

func mustEqualFiles(t *testing.T, src, dst string) {
	t.Helper()
	want, err := os.ReadFile(src)
	if err != nil {
		t.Fatal(err)
	}
	got, err := os.ReadFile(dst)
	if err != nil {
		t.Fatal(err)
	}
	if string(want) != string(got) {
		t.Fatalf("live file %s does not match %s", dst, src)
	}
}

func TestInstalledOverlayMatchesSource(t *testing.T) {
	mustEqualFiles(t, "profiles/personal.toml", overlayPath)
}

func TestDprintAvailableInPersonalCheckouts(t *testing.T) {
	mise := lookPath(t, "mise")
	here, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for _, dir := range []string{personalRepo, here} {
		t.Run(filepath.Base(dir), func(t *testing.T) {
			which, err := run(t, dir, mise, 30*time.Second, "which", "dprint")
			if err != nil {
				t.Fatalf("mise which dprint in %s: %v\n%s", dir, err, which)
			}
			if strings.TrimSpace(which) == "" {
				t.Fatalf("mise which dprint empty in %s", dir)
			}
			if _, lookErr := exec.LookPath("dprint"); lookErr != nil {
				t.Fatalf("command -v dprint failed in %s: %v", dir, lookErr)
			}
		})
	}
}

func TestInstalledDprintConfigMatchesSource(t *testing.T) {
	mustEqualFiles(t, "format/personal.jsonc", dprintConfig)
}

func TestDprintCheckThisRepo(t *testing.T) {
	dprint := lookPath(t, "dprint")
	here, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	out, err := run(t, here, dprint, 3*time.Minute, "check")
	if err != nil {
		t.Fatalf("dprint check: %v\n%s", err, out)
	}
}

func TestMiseDepsListsUvForPersonalOverlay(t *testing.T) {
	mise := lookPath(t, "mise")
	overlayRoot := filepath.Dir(overlayPath)
	rootList, err := run(t, overlayRoot, mise, 30*time.Second, "deps", "install", "--list")
	if err != nil {
		t.Fatalf("mise deps install --list in overlay root: %v\n%s", err, rootList)
	}
	if !strings.Contains(rootList, "uv") {
		t.Fatalf("personal overlay deps list missing uv\n%s", rootList)
	}
	cfg, err := run(t, personalRepo, mise, 30*time.Second, "config", "get", "--file", overlayPath, "deps")
	if err != nil {
		t.Fatalf("mise config get deps from attention-mail: %v\n%s", err, cfg)
	}
	if !strings.Contains(cfg, "uv") {
		t.Fatalf("personal overlay deps from attention-mail missing uv\n%s", cfg)
	}
	list, err := run(t, personalRepo, mise, 30*time.Second, "deps", "install", "--list")
	if err != nil {
		t.Fatalf("mise deps install --list in attention-mail: %v\n%s", err, list)
	}
	if !strings.Contains(list, "uv") && !strings.Contains(cfg, "[uv]") {
		t.Fatalf("attention-mail did not see uv from the Personal overlay\nlist:\n%s\ncfg:\n%s", list, cfg)
	}
}

func TestCompanyDepsDoesNotLeakPersonalOverlay(t *testing.T) {
	mise := lookPath(t, "mise")
	ls, err := run(t, companyRepo, mise, 30*time.Second, "config", "ls")
	if err != nil {
		t.Fatalf("mise config ls in company repo: %v\n%s", err, ls)
	}
	if strings.Contains(ls, "Developer/Personal/mise.toml") {
		t.Fatalf("personal overlay leaked into company mise config ls\n%s", ls)
	}
	list, err := run(t, companyRepo, mise, 30*time.Second, "deps", "install", "--list")
	if err != nil {
		t.Fatalf("mise deps install --list in company repo: %v\n%s", err, list)
	}
	if strings.Contains(list, "Developer/Personal") {
		t.Fatalf("personal overlay leaked into company deps list\n%s", list)
	}
}

func TestWorktrunkConfigInstalled(t *testing.T) {
	mustEqualFiles(t, "worktrunk/config.toml", worktrunkConfig)
	wt := lookPath(t, "wt")
	here, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	out, err := run(t, here, wt, 30*time.Second, "config", "show")
	if err != nil {
		t.Fatalf("wt config show: %v\n%s", err, out)
	}
	if !strings.Contains(out, "USER CONFIG") || !strings.Contains(out, "worktrunk/config.toml") {
		t.Fatalf("wt config show did not find ~/.config/worktrunk/config.toml\n%s", out)
	}
	if !strings.Contains(out, worktreePath) {
		t.Fatalf("wt config show missing worktree-path template\n%s", out)
	}
}

func TestCowtreeCompactDryRunThisRepo(t *testing.T) {
	cowtree := lookPath(t, "cowtree")
	here, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	out, err := run(t, here, cowtree, 30*time.Second, "compact", "--all", "--dry-run")
	if err != nil {
		t.Fatalf("cowtree compact --all --dry-run: %v\n%s", err, out)
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
