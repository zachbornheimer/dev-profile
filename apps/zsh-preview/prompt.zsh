# Colorful overrides layered on the original prompt; enabled by ~/.zshrc.local.
builtin source "$HOME/.config/zsh-preview/routes.zsh"
(( ${+functions[_preview_git_base]} )) || functions[_preview_git_base]=$functions[_p_git_compute]
(( ${+functions[_preview_dir_base]} )) || functions[_preview_dir_base]=$functions[_p_dir_update]
typeset -g _preview_url="" _preview_project=""
_p_c[cyan]='%F{#89dceb}'
_p_c[magenta]='%F{#f5a0d5}'
_p_c[amber]='%F{#f9e2af}'
_p_c[red]='%F{#f38ba8}'
_p_c[green]='%F{#a6e3a1}'
_p_c[blue]='%F{#89b4fa}'

prompt::git-segment() {
  local branch=$1 changes=$2 ahead=$3 behind=$4 stash=$5 action=$6
  [[ -n $branch ]] || return 0
  local segment="%B${_p_c[magenta]} ${branch//\%/%%}${_p_c[rst]}%b"
  [[ -n $changes ]] && segment+="${_p_c[amber]}${changes}${_p_c[rst]}"
  ((ahead)) && segment+=" ${_p_c[cyan]}↑${ahead}${_p_c[rst]}"
  ((behind)) && segment+=" ${_p_c[amber]}↓${behind}${_p_c[rst]}"
  ((stash)) && segment+=" ${_p_c[magenta]}⚑${stash}${_p_c[rst]}"
  [[ -n $action ]] && segment+=" %B${_p_c[red]}${action//\%/%%}${_p_c[rst]}%b"
  print -r -- "$segment"
}

_p_git_compute() {
  local data=$(_preview_git_base) row x y
  [[ -n $data ]] || return 0
  local -a fields=("${(@s:|:)data}")
  local -i staged=0 modified=0 untracked=0 conflicts=0
  while IFS= read -r -d '' row; do
    x=${row[1]} y=${row[2]}
    if [[ $x$y == '??' ]]; then
      ((untracked++))
    elif [[ $x$y == (DD|AU|UD|UA|DU|AA|UU) ]]; then
      ((conflicts++))
    else
      [[ $x != ' ' ]] && ((staged++))
      [[ $y != ' ' ]] && ((modified++))
    fi
    [[ $x == [RC] ]] && IFS= read -r -d '' row
  done < <(command git status --porcelain -z --ignore-submodules 2>/dev/null)
  local changes=""
  ((staged)) && changes+=" +$staged"
  ((modified)) && changes+=" ~$modified"
  ((untracked)) && changes+=" ?$untracked"
  ((conflicts)) && changes+=" !$conflicts"
  local common=$(command git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)
  local project=${common:h:t}
  printf '%s|%s|%s|%s|%s|%s|%s|%s\n' "$fields[1]" "$changes" "$fields[3]" "$fields[4]" "$fields[5]" "$fields[6]" "$(preview::selected-urls "$_p_repo_root")" "$project"
}

_p_dir_update() {
  _preview_url="" _preview_project=""
  _preview_dir_base
}

_p_async_done() {
  local fd=$1 data="$(<&$1)"
  zle -F "$fd" 2>/dev/null
  exec {fd}<&-
  _p_git_fd=0
  local -a fields=("${(@s:|:)data}")
  _p_git=$(prompt::git-segment "${fields[1]:-}" "${fields[2]:-}" "${fields[3]:-0}" "${fields[4]:-0}" "${fields[5]:-0}" "${fields[6]:-}")
  _preview_url=${fields[7]:-}
  _preview_project=${fields[8]:-}
  prompt::build
  zle reset-prompt
}

preview::width() {
  emulate -L zsh
  setopt extendedglob
  local visible=${(%)1}
  visible=${visible//$'\e'\[[0-9\;:]#m/}
  print -r -- "${(m)#visible}"
}

preview::header() {
  local left=$1 right=$2
  [[ -n $right ]] || { print -r -- "$left"; return; }
  local -i left_width=$(preview::width "$left")
  local -i right_width=$(preview::width "$right")
  local -i gap=$((COLUMNS - left_width - right_width - 1))
  if ((gap >= 2)); then
    print -r -- "$left${(pl:gap:: :)}$right"
  else
    print -r -- "$left"$'\n'"$right"
  fi
}

prompt::build() {
  local directory="$(prompt::path)" mark=${_p_c[green]} guard=""
  [[ -n $_preview_project ]] && directory="$_preview_project${PWD#$_p_repo_root}"
  directory=${directory//\%/%%}
  [[ -n $SSH_CONNECTION ]] && guard="${_p_c[blue]}%n@%m${_p_c[rst]} in "
  ((EUID == 0)) && guard="%B${_p_c[red]}%n${_p_c[rst]}%b in "
  local line="${guard}%B${_p_c[cyan]}${directory}${_p_c[rst]}%b"
  [[ -n $_p_git ]] && line+=" on $_p_git"
  if [[ -n $AWS_PROFILE && $_p_aws_seen == 1 ]]; then
    local color=${_p_c[amber]}
    [[ $AWS_PROFILE == (*prod*|*production*|*prd*) ]] && color=${_p_c[red]}
    line+="  %B${color}aws:${AWS_PROFILE//\%/%%}${_p_c[rst]}%b"
  fi
  if ((_p_dur >= _p_dur_min)); then
    line+=" %B${_p_c[amber]}took $(prompt::fmt-dur "$_p_dur")${_p_c[rst]}%b"
  fi
  local url="${_preview_url//$'\n'/ · }" right=""
  [[ -n $url ]] && right="${_p_c[blue]}${url//\%/%%}${_p_c[rst]}"
  line=$(preview::header "$line" "$right")
  ((_p_exit)) && mark=${_p_c[red]}
  PROMPT="$line"$'\n'"%B${mark}❯${_p_c[rst]}%b "
  RPROMPT=""
  ((_p_exit)) && RPROMPT="%B${_p_c[red]}exit $_p_exit${_p_c[rst]}%b"
  return 0
}
