alias e='nvim'
alias n='nvim'
alias vi='nvim'
alias vim='nvim'
alias view='nvim -R'

alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias -- -='cd -'
mkcd() { mkdir -p -- "$1" && cd -- "$1" || return; }
alias take=mkcd
alias reload='exec zsh'
alias myip='curl -s ifconfig.me'

alias brew-maint-now='~/.local/bin/brew-maintenance'
alias macos-updates-on='~/.local/bin/macos-security-updates-on'

# System
alias dns='sudo killall -HUP mDNSResponder'
alias copy-ssh='cat ~/.ssh/id_rsa.pub | pbcopy && __ -t success "SSH key copied."'

alias dotfiles-add='dotfiles-capture'

# Super Shorthands
# Recommended modern CLI tools:
#   brew install ripgrep fd bat eza dust bottom procs sd hyperfine git-delta zoxide
#
# Keep the macOS/POSIX commands (grep/find/cat/ls/ps/sed) intact for scripts.
# These aliases are intentionally interactive-only conveniences.
alias g='git'
alias f='fd'
alias b='btm'
alias d='dust'
alias l='eza --group-directories-first'
alias tree='eza --tree --group-directories-first'
alias ccat='bat'
alias p='procs'
alias bench='hyperfine'

# The "I just want to see what's happening" monitor
alias monitor='btm'

alias append-pdf='perl /Users/zbornheimer/scripts/perl/append-pdf.pl'
alias bob='opssh id-rsa-bob lessonbrm@lessonbrm.ssh.wpengine.net'
alias cai='/Applications/Cursor.app/Contents/MacOS/Cursor '
alias clean-pyc='find . -name "*.pyc" -exec rm -f {} \; && find . -type d -name "__pycache__" -exec rm -rf {} +'
alias clean_pyc='find . -name "*.pyc" -exec rm -f {} \; && find . -type d -name "__pycache__" -exec rm -rf {} +'
alias clear-pyc='find . -name "*.pyc" -exec rm -f {} \; && find . -type d -name "__pycache__" -exec rm -rf {} +'
alias clear_pyc='find . -name "*.pyc" -exec rm -f {} \; && find . -type d -name "__pycache__" -exec rm -rf {} +'
alias crypto='sh /Users/zbornheimer/scripts/shell\ scripts/crypto-to-clipboard.sh'
alias crypto-wallet='sh /Users/zbornheimer/scripts/shell\ scripts/crypto-wallet-to-clipboard.sh'
alias delds='find . -name '\''.DS_Store'\'' -delete'
alias dperl='perl -I. -d:NYTProf '
alias ds-clean='find . -name ".DS_Store" -delete'
alias eapp='opssh eapp-private-key bitnami@54.158.79.237'
alias fademp3='sh /Users/zbornheimer/scripts/shell\ scripts/fadeMP3.sh'
alias ibd='perl scripts/perl/stocks/ibd.pl'
alias isjac='opssh id-rsa isjac@isjac.ssh.wpengine.net'
alias maria-pack='perl /Users/zbornheimer/scripts/perl/maria/standardize-sheet-music.pl'
alias perl='perl -I.'
alias prepend-pdf='perl /Users/zbornheimer/scripts/perl/prepend-pdf.pl'
alias psn=/Users/zbornheimer/scripts/perl/maria/parts_score_namer.pl
alias run-help=man
alias rvm-restart='rvm_reload_flag=1 source '\''/Users/zbornheimer/.rvm/scripts/rvm'\'
alias sahbank='perl /Users/zbornheimer/Dropbox/Zysys/BestPlanPro/do-statements.pl'
alias speed='speedtest --single --simple 2>/dev/null'
alias sv='uv run -- python -m http.server '
alias srv='uv run -- python -m http.server '

alias ttc='ssh forge@3.141.139.173'
alias unlock_all_pdfs='find . -iname "*.pdf" -exec qpdf --decrypt --replace-input "{}" \;'
alias unlock_pdf='qpdf --decrypt --replace-input'
alias update-financials='sh /Users/zbornheimer/scripts/shell\ scripts/update-financials.sh'
alias wav2mp3='for i in *.wav; do ffmpeg -i "$i" -ab 320k "${i%.*}.mp3"; done'
alias which-command=whence
zab-update() {
	__ -t pending "Updating ZAB AI" -- zsh -c 'python3 -m pip uninstall -y zab_ai >/dev/null && python3 -m pip install -q git+https://github.com/ZAB-AI-LLC/python-lib.git@main'
}
alias zbm='opssh id-rsa-zbm zbm@zbm.ssh.wpengine.net'
alias zbm-insta='perl /Users/zbornheimer/scripts/perl/insta-music-share/insta-music-share.pl'
alias zysys='opssh zysys-hosting-key ec2-user@srv1.web.zysyshosting.com'
alias hide-desktop-icons='defaults write com.apple.finder CreateDesktop -bool false; killall Finder'
alias show-desktop-icons='defaults write com.apple.finder CreateDesktop -bool true; killall Finder'

# cp is ~/.local/bin/cp → cpx (APFS reflink auto). Apple cp remains /bin/cp.
alias bcp="/bin/cp"

alias hd="hunk diff"
