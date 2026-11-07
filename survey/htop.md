`apps/htop` is `htoprc`, the htop settings file, tracked as `~/.config/htop`. Its header warns that htop rewrites it whenever settings change in the UI. It sorts by key 46, hides kernel threads, shows full program paths, and uses a 1.5 s refresh (`delay=15`, in tenths of a second). The meters are CPUs, memory and swap on the left, and CPUs, tasks, load average and uptime on the right.

It is not tested. `config/mise.toml` is the only reference (`track`, `encrypt = true`). Since htop rewrites the file, the tracked copy can drift from the live one without any check noticing.
