#compdef dead-projects-society
# zsh completion for dead-projects-society
# Install: copy to a directory on your $fpath (e.g. ~/.zsh/completions/_dead-projects-society, renamed with the underscore)
# Generated from the CLI's own --help (v0.25 flag set). Regenerate when flags change.
_dead_projects_society() {
  _arguments \
    '--adopt[file to write adoption papers to]:file:_files' \
    '--autopsy[append the metadata autopsy to the report]' \
    '--badge[file to write the README badge to]:file:_files' \
    '--card[file to write the share card to]:file:_files' \
    '--certificates[directory for certificates]:directory:_files -/' \
    '--days[days of silence that mean death]:days:' \
    '--deep-autopsy[opt-in code-aware Ember autopsy]' \
    '--deep-budget[hard spend cap in USD]:usd:' \
    '--deep-dry-run[price the deep autopsy without calling]' \
    '--deep-ledger[spend ledger file]:file:_files' \
    '--deep-max-tokens[sample token cap]:tokens:' \
    '--deep-model[model id]:model:' \
    '--depth[folder depth to scan]:depth:' \
    '--diff[compare with the last recorded visit]' \
    '--exclude[directory name to skip]:name:' \
    '--fail-if-new-deaths[exit 3 when the log reports a new death]' \
    '--html[file to write the HTML graveyard to]:file:_files' \
    '--json[print the full record as JSON]' \
    '--on-this-day[anniversaries in the grounds]' \
    '--oneline[one line per project]' \
    '--out[file to write Markdown obituaries to]:file:_files' \
    '--site[directory for the web graveyard data]:directory:_files -/' \
    '--square[file to write the square card to]:file:_files' \
    '--state[groundskeeper state file]:file:_files' \
    '--version[print the version]' \
    '--wrapped-kit[directory for the Wrapped kit]:directory:_files -/' \
    '--year[year for the Wrapped kit]:year:' \
    '*:grounds directory:_files -/'
}
_dead_projects_society "$@"
