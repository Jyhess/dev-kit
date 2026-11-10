# Shared zsh configuration of dev-kit (macOS). Sourced from ~/.zshrc, which
# keeps the machine-specific lines (PATH, nvm, direnv…).

_devkit_terminal="${${(%):-%x}:A:h:h}"

# oh-my-zsh, without a theme: starship draws the prompt
export ZSH="${ZSH:-$HOME/.oh-my-zsh}"
ZSH_THEME=""
COMPLETION_WAITING_DOTS="true"
HIST_STAMPS="mm/dd/yyyy"
plugins=(z zsh-autosuggestions zsh-syntax-highlighting)
[[ -r "$ZSH/oh-my-zsh.sh" ]] && source "$ZSH/oh-my-zsh.sh"

export EDITOR=vim
export PAGER="less -SFX"

# Prompt shared with Windows: terminal/starship.toml
export STARSHIP_CONFIG="$_devkit_terminal/starship.toml"
(( $+commands[starship] )) && [[ -o interactive ]] && eval "$(starship init zsh)"

# Git
alias gr='git rebase'
alias gs='git status'
alias gl='git log --oneline'
alias glog='git log --oneline'
alias gp='git push'
alias gpf='git push --force-with-lease'

# origin's default branch (`origin/main`), else origin/main or origin/master
_devkit_main_branch() {
  git rev-parse --abbrev-ref --quiet origin/HEAD 2>/dev/null && return
  git rev-parse --verify --quiet origin/main >/dev/null && echo origin/main || echo origin/master
}

# The Git rule of AGENTS.md: fetch, then rebase on origin's default branch, local changes kept
grim() { git fetch --quiet && git rebase -i --autostash "$(_devkit_main_branch)" "$@" }
grum() { git fetch --quiet && git rebase --autostash "$(_devkit_main_branch)" "$@" }

# Docker Compose
up() { docker compose up -d "$@" }
alias down='docker compose down'
alias logs='docker compose logs'

autoload -Uz add-zsh-hook

# .NET aliases, only in a .NET project: a .sln, .csproj or .fsproj in the
# current folder or a parent up to the repository root (outside a repository,
# the current folder only).
typeset -gA _devkit_dotnet=(dw watch db build dc clean dt test dr run)

_devkit_in_dotnet_project() {
  setopt localoptions extendedglob
  local dir="$PWD" root
  local -a found
  root="$(git rev-parse --show-toplevel 2>/dev/null)" || root="$PWD"
  while true; do
    found=($dir/*.(sln|csproj|fsproj)(N[1]))
    (( $#found )) && return 0
    [[ "$dir" == "$root" || "$dir" == / ]] && return 1
    dir="${dir:h}"
  done
}

_devkit_dotnet_aliases() {
  local name
  if _devkit_in_dotnet_project; then
    for name in ${(k)_devkit_dotnet}; do alias $name="dotnet $_devkit_dotnet[$name]"; done
  else
    for name in ${(k)_devkit_dotnet}; do (( $+aliases[$name] )) && unalias $name; done
  fi
  return 0
}

add-zsh-hook chpwd _devkit_dotnet_aliases
_devkit_dotnet_aliases

# Background fetch, at most every 5 minutes per repository, so that the prompt
# knows when a pull is needed. Silent, never asks for credentials.
_devkit_fetch() {
  local git_dir
  local -a recent
  git_dir="$(git rev-parse --absolute-git-dir 2>/dev/null)" || return 0
  [[ -n "$(git remote 2>/dev/null)" ]] || return 0
  recent=($git_dir/FETCH_HEAD(N.mm-5))
  (( $#recent )) && return 0
  touch "$git_dir/FETCH_HEAD"
  GIT_TERMINAL_PROMPT=0 GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes}" \
    git fetch --quiet >/dev/null 2>&1 &!
}

add-zsh-hook precmd _devkit_fetch
