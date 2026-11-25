/* Dead Projects Society — platform application.
   A static, data-driven app. All content comes from data.json.
   The grounds currently hold no burials: every view renders an
   intentional empty state until records are added to data.json. */
(function () {
  "use strict";

  var EMPTY = {
    counts: { cataloged: 0, buried: 0, verified: 0, open_adoptions: 0, wards: 0 },
    records: [], honors: [], infamy: [], public_honours: []
  };
  var DATA = EMPTY;

  var state = {
    q: "", division: "all", year: "all", lang: "all", tag: "all",
    view: "grid", sort: "grounds"
  };

  /* ---------- helpers ---------- */

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function num(n) { return Number(n).toLocaleString("en-US"); }
  function byId(id) { return DATA.records.filter(function (r) { return r.id === id; })[0] || null; }
  function yearsLabel(r) { return r.born + " – " + r.died; }
  function lifespanLabel(r) {
    if (r.lifespan_years < 1) return "under a year";
    return (Math.round(r.lifespan_years * 10) / 10) + " years";
  }
  function silenceLabel(r) {
    if (r.silence_days == null) return "—";
    if (r.silence_days >= 730) return num(r.silence_days) + " days (" + (Math.round(r.silence_days / 365.25 * 10) / 10) + " years)";
    return num(r.silence_days) + " days";
  }
  function divisionLabel(r) {
    if (r.division === "public") return r.kind === "product" ? "Public Grounds · Product" : "Public Grounds · Repository";
    if (r.division === "society") return "Society Grounds";
    return "The Wards";
  }
  function statusBadge(r) {
    if (r.status === "coma") return '<span class="badge ward">Intensive care</span>';
    if (r.status === "alive") return '<span class="badge ward">Still breathing</span>';
    if (r.adoptable) return '<span class="badge adopt">Adoption open</span>';
    return '<span class="badge">At rest</span>';
  }

  /* ---------- filtering ---------- */

  function filtered() {
    var q = state.q.trim().toLowerCase();
    var out = DATA.records.filter(function (r) {
      if (state.division !== "all") {
        if (state.division === "public-products" && !(r.division === "public" && r.kind === "product")) return false;
        if (state.division === "public-repos" && !(r.division === "public" && r.kind === "repository")) return false;
        if (state.division === "society" && r.division !== "society") return false;
        if (state.division === "wards" && r.division !== "wards") return false;
      }
      if (state.year !== "all" && r.died !== state.year) return false;
      if (state.lang !== "all" && (r.tech || []).indexOf(state.lang) === -1) return false;
      if (state.tag !== "all" && r.cause_tag !== state.tag) return false;
      if (q) {
        var hay = (r.name + " " + (r.tech || []).join(" ") + " " + (r.cause || "") + " " +
          (r.epitaph || "") + " " + (r.description || "")).toLowerCase();
        if (hay.indexOf(q) === -1) return false;
      }
      return true;
    });
    var by = {
      grounds: null,
      silence: function (a, b) { return (b.silence_days || 0) - (a.silence_days || 0); },
      life: function (a, b) { return b.lifespan_years - a.lifespan_years; },
      stars: function (a, b) { return (b.stars || 0) - (a.stars || 0); },
      name: function (a, b) { return a.name.localeCompare(b.name); },
      newest: function (a, b) { return String(b.died).localeCompare(String(a.died)); },
      oldest: function (a, b) { return String(a.died).localeCompare(String(b.died)); }
    }[state.sort];
    if (by) out = out.slice().sort(by);
    return out;
  }

  function optionList(values, current, allLabel) {
    var h = '<option value="all">' + esc(allLabel) + "</option>";
    values.forEach(function (v) {
      h += '<option value="' + esc(v) + '"' + (current === v ? " selected" : "") + ">" + esc(v) + "</option>";
    });
    return h;
  }
  function distinct(key) {
    var seen = {};
    DATA.records.forEach(function (r) {
      if (key === "tech") (r.tech || []).forEach(function (t) { seen[t] = 1; });
      else if (r[key]) seen[r[key]] = 1;
    });
    return Object.keys(seen).sort();
  }

  /* ---------- home / graveyard ---------- */

  function countsHTML() {
    var c = DATA.counts;
    function card(n, label) {
      return '<div class="count-card"><span class="count-num">' + num(n) + '</span>' +
        '<span class="count-label">' + label + "</span></div>";
    }
    return '<div class="counts">' +
      card(c.cataloged, "Cataloged") +
      card(c.verified, "Verified burials") +
      card(c.open_adoptions, "Open adoptions") +
      card(c.wards, "In the wards") +
      "</div>";
  }

  function controlsHTML() {
    var divs = [
      ["all", "All divisions"], ["public-products", "Public Grounds · Products"],
      ["public-repos", "Public Grounds · Repositories"], ["society", "Society Grounds"],
      ["wards", "The Wards"]
    ];
    var divOpts = divs.map(function (d) {
      return '<option value="' + d[0] + '"' + (state.division === d[0] ? " selected" : "") + ">" + d[1] + "</option>";
    }).join("");
    var sorts = [
      ["grounds", "As cataloged"], ["silence", "Longest silence"], ["life", "Longest life"],
      ["stars", "Most stars"], ["name", "Name"], ["newest", "Newest death"], ["oldest", "Oldest death"]
    ];
    var sortOpts = sorts.map(function (s) {
      return '<option value="' + s[0] + '"' + (state.sort === s[0] ? " selected" : "") + ">" + s[1] + "</option>";
    }).join("");
    function vbtn(v, label) {
      return '<button type="button" data-action="view" data-view="' + v + '"' +
        (state.view === v ? ' class="active"' : "") + ">" + label + "</button>";
    }
    return '<div class="controls">' +
      '<div><label for="f-q">Search the dead</label>' +
      '<input id="f-q" type="search" placeholder="Search the dead&hellip;" value="' + esc(state.q) + '"></div>' +
      '<div class="filter-row">' +
      '<div><label for="f-division">Division</label><select id="f-division">' + divOpts + "</select></div>" +
      '<div><label for="f-year">Year</label><select id="f-year">' + optionList(distinct("died"), state.year, "All years") + "</select></div>" +
      '<div><label for="f-lang">Language / field</label><select id="f-lang">' + optionList(distinct("tech"), state.lang, "All languages") + "</select></div>" +
      '<div><label for="f-tag">Tag</label><select id="f-tag">' + optionList(distinct("cause_tag"), state.tag, "All causes") + "</select></div>" +
      '<div><label for="f-sort">Order</label><select id="f-sort">' + sortOpts + "</select></div>" +
      '<div><label>View</label><div class="view-toggle">' + vbtn("grid", "Grid") + vbtn("list", "List") + vbtn("timeline", "Timeline") + "</div></div>" +
      "</div></div>";
  }

  function emptyGroundsHTML() {
    return '<div class="empty"><span class="empty-mark">&#9760;</span>' +
      "<h2>The grounds are consecrated. No burials yet.</h2>" +
      "<p>The Society has prepared these grounds and opened the registry, but no project " +
      "has been laid to rest here yet. When the first verified burials are recorded, their " +
      "stones, obituaries, and autopsies will stand on this page.</p>" +
      "<p>Until then, the gates are open and the grass is undisturbed.</p></div>";
  }
  function noMatchHTML() {
    return '<div class="empty"><span class="empty-mark">&#10013;</span>' +
      "<h2>No grave matches that search.</h2>" +
      "<p>The dead keep their names. Try a different name, or loosen the filters.</p></div>";
  }

  function stoneHTML(r) {
    return '<a class="stone" href="#/project/' + esc(r.id) + '">' +
      '<div class="stone-name">' + esc(r.name) + "</div>" +
      '<div class="stone-years">' + esc(yearsLabel(r)) + "</div>" +
      '<div class="stone-epitaph">&ldquo;' + esc(r.epitaph || "") + "&rdquo;</div>" +
      '<div class="stone-meta">' + esc(r.cause_tag || divisionLabel(r)) +
      (r.silence_days != null ? " · silent " + num(r.silence_days) + " days" : "") +
      (r.stars ? " · " + num(r.stars) + " stars" : "") + "</div>" +
      statusBadge(r) + "</a>";
  }

  function resultsHTML() {
    var list = filtered();
    if (!list.length) return DATA.records.length ? noMatchHTML() : emptyGroundsHTML();
    if (state.view === "list") {
      var rows = list.map(function (r) {
        return "<tr><td><a href=\"#/project/" + esc(r.id) + "\">" + esc(r.name) + "</a></td>" +
          "<td>" + esc(yearsLabel(r)) + "</td><td>" + esc(divisionLabel(r)) + "</td>" +
          "<td>" + esc(r.cause_tag || "—") + "</td>" +
          "<td>" + (r.silence_days != null ? num(r.silence_days) + " days" : "—") + "</td>" +
          "<td>" + (r.condition_score != null ? r.condition_score + "/100" : "—") + "</td></tr>";
      }).join("");
      return '<table class="list-table"><thead><tr><th>Name</th><th>Years</th><th>Division</th>' +
        "<th>Cause</th><th>Silence</th><th>Condition</th></tr></thead><tbody>" + rows + "</tbody></table>";
    }
    if (state.view === "timeline") {
      var byYear = {};
      list.forEach(function (r) { (byYear[r.died] = byYear[r.died] || []).push(r); });
      return '<div class="timeline">' + Object.keys(byYear).sort().reverse().map(function (y) {
        return '<div class="timeline-year">' + esc(y) + "</div>" + byYear[y].map(function (r) {
          return '<div class="timeline-item"><a class="t-name" href="#/project/' + esc(r.id) + '">' +
            esc(r.name) + '</a> <span class="t-meta">' + esc(r.cause_tag || "") +
            " · lived " + esc(lifespanLabel(r)) + " · silent " + (r.silence_days != null ? num(r.silence_days) + " days" : "—") + "</span></div>";
        }).join("");
      }).join("") + "</div>";
    }
    return '<div class="grid">' + list.map(stoneHTML).join("") + "</div>";
  }

  function homeHTML() {
    return '<section class="hero"><h1>The Cemetery Awaits</h1>' +
      "<p>Independent software preservation, forensic project autopsies, and governed resurrection, " +
      "stewarded by Ghost Developer Studio. Memorialization and public browsing are free in perpetuity.</p></section>" +
      countsHTML() + controlsHTML() +
      '<div id="results">' + resultsHTML() + "</div>";
  }

  /* ---------- exports ---------- */

  function certSVG(r) {
    var title = "Certificate of Death";
    return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="560" viewBox="0 0 800 560">' +
      '<rect width="800" height="560" fill="#10141a"/>' +
      '<rect x="24" y="24" width="752" height="512" fill="none" stroke="#b08d57" stroke-width="2"/>' +
      '<rect x="36" y="36" width="728" height="488" fill="none" stroke="#333d46" stroke-width="1"/>' +
      '<text x="400" y="105" text-anchor="middle" font-family="Georgia, serif" font-size="21" letter-spacing="6" fill="#b08d57">DEAD PROJECTS SOCIETY</text>' +
      '<text x="400" y="155" text-anchor="middle" font-family="Georgia, serif" font-size="34" fill="#cfd6dd">' + title + "</text>" +
      '<text x="400" y="205" text-anchor="middle" font-family="Georgia, serif" font-style="italic" font-size="16" fill="#8b96a0">This certifies that the project known as</text>' +
      '<text x="400" y="262" text-anchor="middle" font-family="Georgia, serif" font-size="40" fill="#cfd6dd">' + esc(r.name) + "</text>" +
      '<text x="400" y="305" text-anchor="middle" font-family="Georgia, serif" font-size="19" fill="#cfd6dd">' + esc(yearsLabel(r)) + "</text>" +
      '<text x="400" y="345" text-anchor="middle" font-family="Georgia, serif" font-style="italic" font-size="16" fill="#8b96a0">Cause of death: ' + esc(r.cause_tag || r.cause || "unrecorded") + "</text>" +
      '<text x="400" y="385" text-anchor="middle" font-family="Georgia, serif" font-style="italic" font-size="15" fill="#8b96a0">&ldquo;' + esc(r.epitaph || "") + "&rdquo;</text>" +
      '<circle cx="400" cy="452" r="34" fill="none" stroke="#b08d57" stroke-width="2"/>' +
      '<text x="400" y="460" text-anchor="middle" font-family="Georgia, serif" font-size="17" fill="#b08d57">DPS</text>' +
      '<text x="400" y="512" text-anchor="middle" font-family="Georgia, serif" font-size="13" fill="#5f6a74">Certificate ' + esc(r.cert_no || "") + " · Issued by the Society</text>" +
      "</svg>";
  }

  function memorialHTML(r) {
    return "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">" +
      "<title>" + esc(r.name) + " — Dead Projects Society</title>" +
      "<style>body{background:#0b0e12;color:#cfd6dd;font-family:Georgia,serif;max-width:44rem;margin:2rem auto;padding:0 1rem;line-height:1.55}" +
      "h1{font-weight:normal}.dim{color:#8b96a0}.brass{color:#b08d57}em{color:#8b96a0}</style></head><body>" +
      "<p class=\"brass\">DEAD PROJECTS SOCIETY</p><h1>" + esc(r.name) + "</h1>" +
      "<p>" + esc(yearsLabel(r)) + " · " + esc(divisionLabel(r)) + "</p>" +
      "<p><em>&ldquo;" + esc(r.epitaph || "") + "&rdquo;</em></p>" +
      "<p>" + esc(r.description || "") + "</p>" +
      "<p class=\"dim\">Cause of death: " + esc(r.cause || "unrecorded") + "<br>" +
      "Lifespan: " + esc(lifespanLabel(r)) + " · Silence: " + esc(silenceLabel(r)) +
      (r.cert_no ? "<br>Certificate " + esc(r.cert_no) : "") + "</p>" +
      "<p class=\"dim\">Software never truly dies. It waits.</p></body></html>";
  }

  function download(filename, content, type) {
    if (typeof document === "undefined" || typeof URL === "undefined" || !URL.createObjectURL) return;
    var blob = new Blob([content], { type: type });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 500);
  }

  /* ---------- project detail ---------- */

  function fact(label, value) {
    return '<div class="fact"><div class="fact-label">' + esc(label) + '</div><div class="fact-value">' + value + "</div></div>";
  }

  function projectHTML(r) {
    if (!r) {
      return '<div class="empty"><span class="empty-mark">&#10013;</span>' +
        "<h2>No such grave is recorded.</h2>" +
        "<p>The registry holds no stone by that name. <a href=\"#/\">Return to the gates.</a></p></div>";
    }
    var h = '<p><a href="#/">&larr; The Graveyard</a></p>';
    h += '<section class="hero" style="padding-top:0.4rem"><h1>' + esc(r.name) + "</h1>" +
      "<p>" + esc(yearsLabel(r)) + " · " + esc(divisionLabel(r)) + "</p>" +
      '<p style="margin-top:0.5rem">' + statusBadge(r) + "</p></section>";

    /* facts */
    var facts = fact("Born", esc(r.born_full || r.born)) +
      fact("Died", esc(r.died_full || r.died)) +
      fact("Lifespan", esc(lifespanLabel(r))) +
      fact("Silence", esc(silenceLabel(r)));
    if (r.commits != null) facts += fact("Commits", num(r.commits));
    if (r.stars) facts += fact("Stars at burial", num(r.stars));
    if (r.tech && r.tech.length) facts += fact("Tongue & trade", esc(r.tech.join(", ")));
    if (r.condition_score != null) facts += fact("Condition score", r.condition_score + "/100");
    if (r.cert_no) facts += fact("Certificate", esc(r.cert_no));
    h += '<div class="panel"><h3>The Record</h3><div class="facts">' + facts + "</div>" +
      (r.url ? '<p style="margin-top:0.8rem">Repository of record: <a href="' + esc(r.url) + '">' + esc(r.url) + "</a></p>" : "") +
      "</div>";

    /* obituary */
    h += '<div class="panel"><h3>Coroner&rsquo;s Obituary</h3>' +
      '<p class="epitaph-big">&ldquo;' + esc(r.epitaph || "") + "&rdquo;</p>" +
      '<p class="obituary">' + esc(r.description || "") + "</p>" +
      (r.cause ? '<p><strong>Cause of death:</strong> ' + esc(r.cause) + "</p>" : "") +
      "</div>";

    /* autopsy */
    h += '<div class="panel" id="autopsy"><h3>Recorded Autopsy</h3>';
    if (r.status !== "buried") {
      h += "<p>The Society does not examine the living. No autopsy has been performed.</p>";
    } else if (r.autopsy) {
      h += "<p>" + esc(r.autopsy.momentum) + "</p>";
      if (r.autopsy.findings && r.autopsy.findings.length) {
        h += "<p><strong>Contributing factors</strong></p><ul>" +
          r.autopsy.findings.map(function (f) { return "<li>" + esc(f) + "</li>"; }).join("") + "</ul>";
      }
      if (r.autopsy.peak_month) h += "<p>Peak month: " + esc(r.autopsy.peak_month) + " (" + num(r.autopsy.peak_commits) + " commits, " + esc(r.autopsy.peak_share_percent) + "% of the life).</p>";
      if (r.autopsy.revival_verdict) h += "<p><strong>Revival verdict:</strong> " + esc(r.autopsy.revival_verdict) + "</p>";
    } else {
      h += "<p><strong>Coroner's verdict:</strong> " + esc(r.cause || "unrecorded") + ".</p>" +
        "<p>The case file records a life of " + esc(lifespanLabel(r)) + ", followed by " + esc(silenceLabel(r)) + " of silence" +
        (r.stars ? ", with " + num(r.stars) + " stars watching at the end" : "") +
        ". No deeper examination is on file for this grave.</p>";
    }
    if (r.condition_score != null) {
      h += '<p class="method-note">Condition score ' + r.condition_score + "/100: the share of this project's recorded " +
        "history it spent alive (lifespan &divide; lifespan + silence), computed by the Society from the record above.</p>";
    }
    h += "</div>";

    /* telemetry */
    h += '<div class="panel"><h3>Telemetry</h3>';
    if (r.activity && r.activity.length) {
      var max = Math.max.apply(null, r.activity.concat([1]));
      h += '<div class="spark">' + r.activity.map(function (v) {
        return '<span style="height:' + Math.max(3, Math.round(v / max * 100)) + '%" title="' + v + ' commits"></span>';
      }).join("") + '</div><div class="spark-caption">Commits per month across the life, oldest to newest.</div>';
      h += "<p>Longest flatline: " + num(r.longest_flatline_days || 0) + " days · Resurrections: " + num(r.resurrections || 0) + "</p>";
    } else {
      h += "<p>No commit telemetry is recorded for this grave. The stone and the obituary are the whole of the evidence.</p>";
    }
    h += '<p><a class="btn" href="#/lab">Open in Resurrection Lab</a></p></div>';

    /* certificate + exports */
    if (r.status === "buried") {
      h += '<div class="panel"><h3>Certificate</h3><div class="cert-wrap">' + certSVG(r) + "</div>" +
        '<div class="export-row">' +
        '<button class="btn" data-action="export" data-kind="svg" data-id="' + esc(r.id) + '">Download SVG certificate</button>' +
        '<button class="btn" data-action="export" data-kind="html" data-id="' + esc(r.id) + '">Download HTML memorial</button>' +
        '<button class="btn" data-action="export" data-kind="json" data-id="' + esc(r.id) + '">Download JSON record</button>' +
        "</div></div>";
    }

    /* adoption */
    h += '<div class="panel"><h3>Available for Adoption</h3>';
    if (r.adoptable) {
      h += "<p>This project's code survives in a public repository, and the Society lists it as open for adoption. " +
        "A new maintainer begins by forking the repository of record and announcing the succession.</p>" +
        '<p><a class="btn primary" href="#/adopt">Read the adoption papers</a> ' +
        '<a class="btn" href="' + esc(r.url) + '">Visit the repository</a></p>';
    } else if (r.status === "buried") {
      h += "<p>No public repository is recorded for this project, so there is nothing the Society can hand over. " +
        "Its memorial, however, is kept in perpetuity.</p>";
    } else {
      h += "<p>The living are not offered for adoption.</p>";
    }
    h += "</div>";

    /* evidence trail */
    var trail = [];
    trail.push([r.born_full || r.born, "Born. The record opens."]);
    if (r.autopsy && r.autopsy.peak_month) trail.push([r.autopsy.peak_month, "Peak of life: " + num(r.autopsy.peak_commits) + " commits in a single month."]);
    if (r.epitaph) trail.push([r.died_full || r.died, "Last words recorded: &ldquo;" + esc(r.epitaph) + "&rdquo;"]);
    trail.push([r.died_full || r.died, r.status === "buried" ? "Pronounced dead. Cause: " + esc(r.cause_tag || r.cause || "unrecorded") + "." : "Last seen. The Society keeps watch."]);
    if (r.silence_days != null && r.status === "buried") trail.push(["Since", "Silent for " + silenceLabel(r) + ", and counting."]);
    h += '<div class="panel"><h3>Lifecycle Evidence Trail</h3><ul class="trail">' +
      trail.map(function (t) { return '<li><span class="trail-when">' + esc(t[0]) + '</span> — <span class="trail-what">' + t[1] + "</span></li>"; }).join("") +
      "</ul></div>";
    return h;
  }

  /* ---------- autopsy department ---------- */

  function autopsyHTML() {
    var buried = DATA.records.filter(function (r) { return r.status === "buried"; });
    var h = '<h2 class="section-title">Autopsy Department</h2>' +
      '<p class="section-sub">Every burial on record, examined. The coroner works from evidence: ' +
      "dates, silence, and whatever the project left behind.</p>";
    if (!buried.length) {
      return h + '<div class="empty"><span class="empty-mark">&#9760;</span>' +
        "<h2>The examination table is empty.</h2>" +
        "<p>No autopsies have been recorded, because no burials have taken place here yet. " +
        "When the first project is laid to rest, its examination will be filed on this page.</p></div>";
    }
    var rows = buried.map(function (r) {
      return "<tr><td><a href=\"#/project/" + esc(r.id) + "\">" + esc(r.name) + "</a></td>" +
        "<td>" + esc(r.cause_tag || "—") + "</td><td>" + esc(lifespanLabel(r)) + "</td>" +
        "<td>" + esc(silenceLabel(r)) + "</td><td>" + (r.condition_score != null ? r.condition_score + "/100" : "—") + "</td>" +
        "<td>" + (r.autopsy && r.autopsy.revival_verdict ? esc(r.autopsy.revival_verdict) : "—") + "</td></tr>";
    }).join("");
    return h + '<table class="list-table"><thead><tr><th>Project</th><th>Cause</th><th>Lifespan</th>' +
      "<th>Silence</th><th>Condition</th><th>Revival verdict</th></tr></thead><tbody>" + rows + "</tbody></table>" +
      '<p class="method-note">Condition score: the share of a project\'s recorded history it spent alive ' +
      "(lifespan &divide; lifespan + silence), computed by the Society from public metadata. " +
      "It describes the shape of a life, not its worth.</p>";
  }

  /* ---------- resurrection lab ---------- */

  function labHTML() {
    var withTelemetry = DATA.records.filter(function (r) { return r.activity && r.activity.length; });
    var forkable = DATA.records.filter(function (r) { return r.adoptable; });
    var risen = DATA.records.filter(function (r) { return (r.resurrections || 0) > 0; });
    var h = '<h2 class="section-title">Resurrection Lab</h2>' +
      '<p class="section-sub">Governed resurrection: the dead return only with a maintainer, a fork, ' +
      "and a public record of the succession. Nothing here rises on its own.</p>";
    h += '<div class="panel"><h3>How a resurrection works</h3>' +
      "<p>1. Choose a grave whose code survives in a public repository.</p>" +
      "<p>2. Fork the repository of record. The fork is the body; the original stone keeps the history.</p>" +
      "<p>3. Announce the succession on the project's adoption papers, so the community that remains can find the new line.</p>" +
      "<p>4. The Society records the resurrection against the original grave. The stone is never erased.</p></div>";
    h += '<div class="panel"><h3>Resurrection Stories</h3>';
    if (risen.length) {
      h += risen.map(function (r) {
        return '<p><a href="#/project/' + esc(r.id) + '">' + esc(r.name) + "</a> — recorded resurrections: " + num(r.resurrections) + ".</p>";
      }).join("");
    } else {
      h += "<p>No resurrections have been recorded yet. The lab is built, staffed, and waiting for its first success.</p>";
    }
    h += "</div>";
    h += '<div class="panel"><h3>Candidates Under Observation</h3>';
    if (withTelemetry.length) {
      h += withTelemetry.map(function (r) {
        return '<p><a href="#/project/' + esc(r.id) + '">' + esc(r.name) + "</a> — longest flatline " +
          num(r.longest_flatline_days || 0) + " days" +
          (r.autopsy && r.autopsy.revival_verdict ? " · verdict: " + esc(r.autopsy.revival_verdict) : "") + "</p>";
      }).join("");
    } else if (forkable.length) {
      h += forkable.map(function (r) {
        return '<p><a href="#/project/' + esc(r.id) + '">' + esc(r.name) + '</a> — code survives; a fork can begin the work.</p>';
      }).join("");
    } else {
      h += "<p>No candidates are under observation. When burials are recorded, the graves whose code survives will be watched from here.</p>";
    }
    h += "</div>";
    return h;
  }

  /* ---------- adoption ---------- */

  function adoptHTML() {
    var open = DATA.records.filter(function (r) { return r.adoptable; });
    var h = '<h2 class="section-title">Adoption &amp; Community</h2>' +
      '<p class="section-sub">The dead deserve heirs. Adoption papers are drawn from the record of each grave: ' +
      "its cause, its estate, and its prospects.</p>";
    h += '<div class="panel"><h3>Terms of adoption</h3>' +
      "<p>An adoption transfers care, not history. The original stone, obituary, and autopsy remain on these grounds forever.</p>" +
      "<p>Where a project's original owner can be reached, their authorization governs the succession. " +
      "Where the code is open source and the owner is gone, a public fork with a public announcement is the Society's recognized line of succession. " +
      "Always check the repository's own licence before building on the estate.</p></div>";
    if (!open.length) {
      return h + '<div class="empty"><span class="empty-mark">&#10013;</span>' +
        "<h2>No graves are open for adoption.</h2>" +
        "<p>There is nothing to hand over yet, because no burials have been recorded here. " +
        "When a project with surviving code is laid to rest, its papers will be posted on this page.</p></div>";
    }
    h += open.map(function (r) {
      return '<div class="panel"><h3>Adoption papers: ' + esc(r.name) + "</h3>" +
        "<p><strong>Estate:</strong> " + esc((r.tech || []).join(", ") || "unrecorded") +
        (r.url ? ' · <a href="' + esc(r.url) + '">repository of record</a>' : "") + "</p>" +
        "<p><strong>Cause of death:</strong> " + esc(r.cause || "unrecorded") + "</p>" +
        "<p><strong>State of the grounds:</strong> silent for " + esc(silenceLabel(r)) +
        ", after a life of " + esc(lifespanLabel(r)) + ".</p>" +
        "<p><strong>Revival outlook:</strong> the code survives in public. A fork and a maintainer are all that is missing.</p>" +
        '<p><a class="btn primary" href="#/project/' + esc(r.id) + '">View the grave</a></p></div>';
    }).join("");
    return h;
  }

  /* ---------- awards ---------- */

  function awardBlock(list, emptyMsg) {
    if (!list.length) return '<div class="empty"><h2>Nothing bestowed yet.</h2><p>' + esc(emptyMsg) + "</p></div>";
    return list.map(function (a) {
      var name = a.project_id && byId(a.project_id)
        ? '<a href="#/project/' + esc(a.project_id) + '">' + esc(a.project_name) + "</a>"
        : esc(a.project_name);
      return '<div class="award"><span class="award-title">' + esc(a.title) + "</span> — " + name +
        '<div class="award-detail">' + esc(a.detail) + (a.basis ? ' <span class="method-note">(' + esc(a.basis) + ")</span>" : "") + "</div></div>";
    }).join("");
  }

  function awardsHTML() {
    var h = '<h2 class="section-title">Society Awards</h2>' +
      '<p class="section-sub">Honours for the dead, bestowed from the record and nothing else.</p>';
    h += '<div class="panel"><h3>Public Grounds Honours</h3>' +
      awardBlock(DATA.public_honours, "The Public Grounds hold no burials yet, so no honours can be computed.") + "</div>";
    h += '<div class="panel"><h3>Society Honors</h3>' +
      awardBlock(DATA.honors, "No honors have been recorded for the Society's own grounds.") + "</div>";
    h += '<div class="panel"><h3>Hall of Infamy</h3>' +
      awardBlock(DATA.infamy, "No infamy has been recorded. The dead rest easy, for now.") + "</div>";
    return h;
  }

  /* ---------- about ---------- */

  function aboutHTML() {
    return '<h2 class="section-title">About &amp; Principles</h2>' +
      '<p class="section-sub">What the Society is, and the rules it keeps.</p>' +
      '<div class="panel"><h3>The Society</h3>' +
      "<p>Dead Projects Society is an independent software preservation project stewarded by Ghost Developer Studio. " +
      "It memorializes abandoned software, examines why it died, and helps the worthy dead find new maintainers.</p>" +
      "<p>Memorialization and public cemetery browsing are free in perpetuity. A grave, once recorded, is never sold or erased.</p></div>" +
      '<div class="panel"><h3>The burial standard</h3>' +
      "<p>No project is buried on a rumor. Products are buried on an official shutdown; repositories on the platform's own archived flag, " +
      "with real star counts and last-push dates. Anything still breathing is refused, however famous. The wards hold the not-yet-dead under observation, unburied.</p></div>" +
      '<div class="panel"><h3>Run it on your own grounds</h3>' +
      "<p>The Society's instrument is a small, free, open-source tool that reads a folder of git repositories and builds a graveyard from their real history: " +
      "obituaries, autopsies, eulogies, certificates, adoption papers, and awards.</p>" +
      '<p><a class="btn" href="https://pypi.org/project/dead-projects-society/">dead-projects-society on PyPI</a> ' +
      '<a class="btn" href="https://github.com/littlestjames82-sys/dead-projects-society">The CLI on GitHub</a> ' +
      '<a class="btn" href="bury.html">Bury a GitHub user</a></p></div>' +
      '<div class="panel"><h3>The Afterlife Network</h3>' +
      "<p>Membership tiers, a public API with badges, and member dashboards are part of the Society's design and are not yet open. " +
      "There is nothing to sign into and nothing to pay for today; this page will say so plainly when that changes.</p></div>";
  }

  /* ---------- router & wiring ---------- */

  var NAV = { home: "home", autopsy: "autopsy", lab: "lab", adopt: "adopt", awards: "awards", about: "about", project: "home" };

  function route() {
    var app = document.getElementById("app");
    if (!app) return;
    var hash = (window.location.hash || "#/").replace(/^#\/?/, "");
    var parts = hash.split("/");
    var page = parts[0] || "home";
    var html, navKey;
    if (page === "project") {
      html = projectHTML(byId(parts.slice(1).join("/")));
      navKey = "home";
    } else if (page === "autopsy") { html = autopsyHTML(); navKey = "autopsy"; }
    else if (page === "lab") { html = labHTML(); navKey = "lab"; }
    else if (page === "adopt") { html = adoptHTML(); navKey = "adopt"; }
    else if (page === "awards") { html = awardsHTML(); navKey = "awards"; }
    else if (page === "about") { html = aboutHTML(); navKey = "about"; }
    else { html = homeHTML(); navKey = "home"; }
    app.innerHTML = html;
    var links = document.querySelectorAll(".site-nav a");
    for (var i = 0; i < links.length; i++) {
      if (links[i].getAttribute("data-nav") === navKey) links[i].classList.add("active");
      else links[i].classList.remove("active");
    }
    if (window.scrollTo) window.scrollTo(0, 0);
  }

  function refreshResults() {
    var el = document.getElementById("results");
    if (el) el.innerHTML = resultsHTML();
  }

  function wire() {
    var app = document.getElementById("app");
    if (!app || !app.addEventListener) return;
    app.addEventListener("input", function (e) {
      if (e.target && e.target.id === "f-q") { state.q = e.target.value; refreshResults(); }
    });
    app.addEventListener("change", function (e) {
      if (!e.target || !e.target.id) return;
      if (e.target.id === "f-division") state.division = e.target.value;
      else if (e.target.id === "f-year") state.year = e.target.value;
      else if (e.target.id === "f-lang") state.lang = e.target.value;
      else if (e.target.id === "f-tag") state.tag = e.target.value;
      else if (e.target.id === "f-sort") state.sort = e.target.value;
      else return;
      refreshResults();
    });
    app.addEventListener("click", function (e) {
      var t = e.target;
      if (!t || !t.getAttribute) return;
      var action = t.getAttribute("data-action");
      if (action === "view") {
        state.view = t.getAttribute("data-view");
        var btns = app.querySelectorAll('[data-action="view"]');
        for (var i = 0; i < btns.length; i++) btns[i].classList.toggle("active", btns[i] === t);
        refreshResults();
      } else if (action === "export") {
        var rec = byId(t.getAttribute("data-id"));
        if (!rec) return;
        var kind = t.getAttribute("data-kind");
        if (kind === "svg") download(rec.id + "-certificate.svg", certSVG(rec), "image/svg+xml");
        else if (kind === "html") download(rec.id + "-memorial.html", memorialHTML(rec), "text/html");
        else if (kind === "json") download(rec.id + ".json", JSON.stringify(rec, null, 2), "application/json");
      }
    });
    if (window.addEventListener) window.addEventListener("hashchange", route);
  }

  function init() {
    wire();
    route();
    if (typeof fetch === "function") {
      fetch("data.json").then(function (res) { return res.json(); }).then(function (json) {
        if (json && json.records) { DATA = json; route(); }
      }).catch(function () { /* keep the empty grounds */ });
    }
  }

  var DPS = {
    EMPTY: EMPTY,
    setData: function (d) { DATA = d || EMPTY; },
    getData: function () { return DATA; },
    state: state,
    views: {
      home: homeHTML, results: resultsHTML, project: projectHTML,
      autopsy: autopsyHTML, lab: labHTML, adopt: adoptHTML,
      awards: awardsHTML, about: aboutHTML
    },
    filtered: filtered,
    certSVG: certSVG,
    memorialHTML: memorialHTML
  };
  if (typeof window !== "undefined") window.DPS = DPS;
  if (typeof document !== "undefined" && document.getElementById && document.getElementById("app")) init();
})();
