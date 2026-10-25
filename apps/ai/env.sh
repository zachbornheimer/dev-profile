# Sourced by shell startup files; preserve the caller's shell options.
ai-env::load() {
    local keys_env="$HOME/.cache/ai/keys.env"
    local template="$HOME/.config/ai/keys.env.op"

    if [[ ! -r "$keys_env" || ! "$keys_env" -nt "$template" ]]; then
        keys_env="$(/bin/zsh -fc 'builtin source "$HOME/.config/zsh/ai-keys.zsh"; ai-keys::env')" || return 1
    fi

    builtin source "$keys_env"
}

ai-env::load
