# bash completion for dead-projects-society
# Install: copy to /etc/bash_completion.d/ or ~/.local/share/bash-completion/completions/
# Generated from the CLI's own --help (v0.25 flag set). Regenerate when flags change.
_dead_projects_society() {
    local cur prev flags file_flags dir_flags
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    flags="--adopt --autopsy --badge --card --certificates --days --deep-autopsy --deep-budget --deep-dry-run --deep-ledger --deep-max-tokens --deep-model --depth --diff --eulogy --exclude --fail-if-new-deaths --html --json --on-this-day --oneline --out --site --square --state --version --wrapped-kit --year --help"
    file_flags="--html --card --square --badge --out --adopt --state --deep-ledger"
    dir_flags="--certificates --site --wrapped-kit"
    case " $file_flags " in
        *" $prev "*) COMPREPLY=( $(compgen -f -- "$cur") ); return 0 ;;
    esac
    case " $dir_flags " in
        *" $prev "*) COMPREPLY=( $(compgen -d -- "$cur") ); return 0 ;;
    esac
    if [[ "$cur" == -* ]]; then
        COMPREPLY=( $(compgen -W "$flags" -- "$cur") )
        return 0
    fi
    COMPREPLY=( $(compgen -d -- "$cur") )
    return 0
}
complete -F _dead_projects_society dead-projects-society
