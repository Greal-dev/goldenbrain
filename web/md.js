// Rôle : rendu Markdown maison — notes du vault, fiches et conversations d'agents. Frontières : renvoie du HTML.
// INV-WEB-1 : tout le texte est échappé AVANT toute balise ; seules les balises émises ici existent (aucun HTML de la source
// n'est interprété) ; les URL sont limitées à http(s) (nouvel onglet, noopener) et à /api/vault/fichier.
// Contexte `ctx` (facultatif) : { liens: Map(cible en minuscules -> chemin|null), depuis: dossier de la note }.
// Avec `liens`, les wikilinks sont résolus sans appel ; sans, ils deviennent des ponts résolus au clic (ponts.js).
import { t } from './langues.js';
const ECH = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const echapper = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ECH[c]);
const desech = (s) => s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
export const urlFichier = (chemin) => `/api/vault/fichier?chemin=${encodeURIComponent(chemin)}`;
const IMG = /\.(png|jpe?g|gif|webp|svg|bmp|avif)$/i, AUDIO = /\.(mp3|wav|ogg|m4a|flac)$/i, PDF = /\.pdf$/i;
// Chemin absolu d'un fichier du vault cité dans une fiche ou une conversation (…\Vault\…\x.md).
const ABS = /(?<![\w\\/])[A-Za-z]:[\\/][^\s`"'<>|*?]*?[\\/]Vault[\\/][^\s`"'<>|*?]*?\.md(?![\w-])/g;
export const relatifVault = (abs) => abs.replace(/^.*?[\\/]Vault[\\/]/i, '').replace(/\\/g, '/');

// Résout un chemin relatif depuis un dossier du vault ; null s'il sort de la racine.
export function joindre(depuis, rel) {
  let r = rel.replace(/[?#].*$/, '');
  try { r = decodeURIComponent(r); } catch { /* tel quel */ }
  const parts = r.startsWith('/') ? [] : depuis.split('/').filter(Boolean);
  for (const s of r.split('/')) {
    if (!s || s === '.') continue;
    if (s === '..') { if (!parts.length) return null; parts.pop(); } else parts.push(s);
  }
  return parts.join('/');
}

const pont = (attrs, html) => `<a class="wl pont" href="#" ${attrs} title="${echapper(t('md.ouvrir_note'))}">${html}</a>`;
const lienNote = (chemin, html) => `<a class="wl" href="#n=${encodeURIComponent(chemin)}" data-note="${echapper(chemin)}">${html}</a>`;
const ext = (u, html) => `<a href="${u}" target="_blank" rel="noopener noreferrer">${html}</a>`;

function fichier(chemin, alt, largeur) {
  const u = urlFichier(chemin);
  if (IMG.test(chemin)) return `<img class="emb" loading="lazy" src="${u}" alt="${alt}"${largeur ? ` width="${largeur}"` : ''}>`;
  if (AUDIO.test(chemin)) return `<audio class="emb" controls preload="none" src="${u}"></audio>`;
  if (PDF.test(chemin)) return `<a class="emb-pdf" href="${u}" target="_blank" rel="noopener noreferrer">${t('md.pdf_ouvrir', { alt })}</a>`;
  return ext(u, alt);
}

function wikilien(emb, interieur, ctx) {
  const brut = desech(interieur);
  const [gauche, ...reste] = brut.split('|');
  const alias = reste.join('|').trim();
  const i = gauche.indexOf('#');
  const cible = (i < 0 ? gauche : gauche.slice(0, i)).trim(), ancre = i < 0 ? '' : gauche.slice(i + 1).trim();
  const taille = emb && /^\d+(x\d+)?$/.test(alias) ? alias.split('x')[0] : '';
  const aff = echapper(taille ? cible : (alias || (ancre && cible ? `${cible} › ${ancre}` : cible || ancre)));
  if (!cible) return `<span class="wl">${aff}</span>`; // [[#ancre]] : même note
  const r = ctx.liens?.get(cible.toLowerCase());
  if (emb) {
    const chemin = typeof r === 'string' ? r : (ctx.depuis !== undefined && /\.\w{2,4}$/.test(cible) ? joindre(ctx.depuis, cible) : null);
    if (chemin && !/\.md$/i.test(chemin)) return fichier(chemin, echapper(cible), taille);
    if (chemin) return lienNote(chemin, `↪ ${aff}`);
    return `<span class="wl a-creer" title="${echapper(t('md.fichier_introuvable'))}">${aff}</span>`;
  }
  if (typeof r === 'string') return lienNote(r, aff);
  if (r === null) return `<a class="wl a-creer" href="#" data-creer="${echapper(cible)}" title="${echapper(t('md.note_a_creer'))}">${aff}</a>`;
  return pont(`data-lien="${echapper(cible)}"`, aff);
}

function lienMd(txt, url, ctx) {
  const u = desech(url.replace(/^&lt;|&gt;$/g, ''));
  if (/^https?:\/\//i.test(u)) return ext(echapper(u), txt);
  if (ctx.depuis === undefined || /^[a-z][a-z0-9+.-]*:/i.test(u) || u.startsWith('#')) return txt;
  const chemin = joindre(ctx.depuis, u);
  if (!chemin) return txt;
  return /\.md$/i.test(chemin) ? lienNote(chemin, txt) : `<a class="wl" href="#f=${encodeURIComponent(chemin)}" data-fichier="${echapper(chemin)}">${txt}</a>`; // lecteur intégré (INV-LECTEUR-1)
}
function imageMd(alt, url, ctx) {
  const u = desech(url.replace(/^&lt;|&gt;$/g, ''));
  if (/^https?:\/\//i.test(u)) return ext(echapper(u), t('md.image_externe', { alt: alt || u })); // la CSP interdit de la charger
  const chemin = ctx.depuis === undefined || /^[a-z][a-z0-9+.-]*:/i.test(u) ? null : joindre(ctx.depuis, u);
  return chemin ? fichier(chemin, alt, '') : alt;
}

function inline(brut, ctx) {
  const pile = [];
  const garder = (html) => `\u0000${pile.push(html) - 1}\u0000`;
  const abs = (s) => s.replace(ABS, (m) => garder(pont(`data-chemin="${echapper(relatifVault(desech(m)))}"`, m)));
  let x = echapper(brut).replace(/\u0000/g, '');
  x = x.replace(/`([^`\n]+)`/g, (_, c) => garder(`<code>${abs(c)}</code>`));
  x = x.replace(/(!?)\[\[([^\]\n]+?)\]\]/g, (_, e, i) => garder(wikilien(!!e, i, ctx)));
  x = x.replace(/!\[([^\]\n]*)\]\((&lt;[^)\n]+?&gt;|[^\s)]+)(?:\s+&quot;[^)]*&quot;)?\)/g, (_, a, u) => garder(imageMd(a, u, ctx)));
  x = x.replace(/\[([^\]\n]+)\]\((&lt;[^)\n]+?&gt;|[^\s)]+)(?:\s+&quot;[^)]*&quot;)?\)/g, (_, a, u) => garder(lienMd(a, u, ctx)));
  x = x.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (_, av, u) => av + garder(ext(u, u)));
  x = abs(x);
  x = x.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  x = x.replace(/~~([^~\n]+)~~/g, '<del>$1</del>');
  x = x.replace(/==([^=\n]+)==/g, '<mark>$1</mark>');
  x = x.replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, '$1<em>$2</em>');
  x = x.replace(/(^|[^_\w])_([^_\n]+)_(?!\w)/g, '$1<em>$2</em>');
  for (let k = 0; k < 3 && x.includes('\u0000'); k++) x = x.replace(/\u0000(\d+)\u0000/g, (_, i) => pile[+i]);
  return x;
}

// --- blocs ---
const REGLE = /^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
const ITEM = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;
const DELIM = /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/;
const OBSIDIAN = new Set(['dataview', 'dataviewjs', 'base']);
const indent = (s) => s.replace(/\t/g, '    ').length - s.replace(/\t/g, '    ').trimStart().length;

function cellules(l) {
  const s = l.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '');
  const out = [];
  let cur = '', code = false, wiki = false;
  for (let k = 0; k < s.length; k++) {
    const c = s[k];
    if (c === '\\' && s[k + 1] === '|') { cur += '|'; k++; continue; }
    if (c === '`') code = !code;
    else if (c === '[' && s[k + 1] === '[') wiki = true;
    else if (c === ']' && s[k + 1] === ']') wiki = false;
    if (c === '|' && !code && !wiki) { out.push(cur.trim()); cur = ''; } else cur += c;
  }
  out.push(cur.trim());
  return out;
}
function tableau(tete, delim, lignes, ctx) {
  const al = cellules(delim).map((c) => (c.startsWith(':') ? (c.endsWith(':') ? 'a-c' : 'a-g') : c.endsWith(':') ? 'a-d' : ''));
  const cel = (tag, c, i) => `<${tag}${al[i] ? ` class="${al[i]}"` : ''}>${inline(c, ctx)}</${tag}>`;
  return `<div class="tbl-wrap"><table class="tbl-note"><thead><tr>${cellules(tete).map((c, i) => cel('th', c, i)).join('')}</tr></thead><tbody>${
    lignes.map((l) => `<tr>${cellules(l).map((c, i) => cel('td', c, i)).join('')}</tr>`).join('')}</tbody></table></div>`;
}

function liste(items, ctx) {
  const out = [], pile = [];
  const fermer = () => { const p = pile.pop(); out.push(`</li></${p.tag}>`); };
  for (const it of items) {
    while (pile.length && it.indent < pile.at(-1).indent) fermer();
    const haut = pile.at(-1);
    if (haut && haut.indent === it.indent && haut.tag === it.tag) out.push('</li>');
    else if (haut && haut.indent === it.indent) { fermer(); pile.push({ indent: it.indent, tag: it.tag }); out.push(`<${it.tag}>`); }
    else { pile.push({ indent: it.indent, tag: it.tag }); out.push(`<${it.tag}>`); }
    let txt = it.lignes.map((l) => inline(l, ctx)).join('<br>');
    const m = /^\[([ xX/-])\]\s+/.exec(it.lignes[0]);
    if (m) {
      txt = it.lignes.map((l, i) => inline(i ? l : l.slice(m[0].length), ctx)).join('<br>');
      txt = `<input type="checkbox" disabled${m[1] === ' ' ? '' : ' checked'} aria-label="${echapper(m[1] === ' ' ? t('md.case_a_faire') : t('md.case_faite'))}"> ${txt}`;
    }
    out.push(`<li${m ? ' class="case-note"' : ''}>${txt}`);
  }
  while (pile.length) fermer();
  return out.join('');
}

function blocs(L, ctx) {
  const out = [], para = [];
  const fin = () => { if (para.length) { out.push(`<p>${para.map((l) => inline(l, ctx)).join('<br>')}</p>`); para.length = 0; } };
  let i = 0;
  while (i < L.length) {
    const l = L[i];
    let m;
    if ((m = /^\s*(`{3,}|~{3,})\s*([\w-]*)/.exec(l))) {
      fin();
      const code = [];
      i++;
      for (; i < L.length; i++) {
        const c = L[i].trim();
        if (c.length >= m[1].length && c === m[1][0].repeat(c.length)) break;
        code.push(L[i]);
      }
      i++;
      const lang = m[2].toLowerCase();
      const pre = `<pre><code>${echapper(code.join('\n'))}</code></pre>`;
      out.push(OBSIDIAN.has(lang) ? `<div class="obs-bloc"><div class="obs-mention">${t('md.bloc_obsidian', { langage: echapper(lang) })}</div>${pre}</div>` : pre);
      continue;
    }
    if (!l.trim()) { fin(); i++; continue; }
    if (/^\s*<!--.*-->\s*$/.test(l)) { fin(); i++; continue; }
    if ((m = /^(#{1,6})\s+(.*?)\s*#*\s*$/.exec(l))) { fin(); const n = Math.min(m[1].length, 4) + 2; out.push(`<h${n}>${inline(m[2], ctx)}</h${n}>`); i++; continue; }
    if (REGLE.test(l)) { fin(); out.push('<hr>'); i++; continue; }
    if (/^\s{0,3}>/.test(l)) {
      fin();
      const interne = [];
      for (; i < L.length && /^\s{0,3}>/.test(L[i]); i++) interne.push(L[i].replace(/^\s{0,3}>\s?/, ''));
      const c = /^\[!(\w+)\][+-]?\s*(.*)$/.exec(interne[0].trim());
      if (c) out.push(`<blockquote class="callout c-${c[1].toLowerCase().replace(/[^a-z]/g, '')}"><div class="callout-titre">${inline(c[2] || c[1], ctx)}</div>${blocs(interne.slice(1), ctx).join('')}</blockquote>`);
      else out.push(`<blockquote>${blocs(interne, ctx).join('')}</blockquote>`);
      continue;
    }
    if (l.includes('|') && i + 1 < L.length && L[i + 1].includes('-') && DELIM.test(L[i + 1])) {
      fin();
      let j = i + 2;
      while (j < L.length && L[j].trim() && L[j].includes('|')) j++;
      out.push(tableau(l, L[i + 1], L.slice(i + 2, j), ctx));
      i = j;
      continue;
    }
    if (ITEM.test(l)) {
      fin();
      const items = [];
      while (i < L.length) {
        const x = L[i];
        const it = ITEM.exec(x);
        if (it && !REGLE.test(x)) items.push({ indent: indent(x), tag: /^\d/.test(it[2]) ? 'ol' : 'ul', lignes: [it[3]] });
        else if (x.trim() && /^\s+\S/.test(x)) items.at(-1).lignes.push(x.trim());
        else if (!x.trim() && i + 1 < L.length && (ITEM.test(L[i + 1]) || /^\s+\S/.test(L[i + 1]))) { /* liste espacée */ } else break;
        i++;
      }
      out.push(liste(items, ctx));
      continue;
    }
    para.push(l);
    i++;
  }
  fin();
  return out;
}

export function md(texte, ctx = {}) {
  return blocs(String(texte ?? '').replace(/\r\n?/g, '\n').split('\n'), ctx).join('');
}
// Seul point d'écriture de HTML : la sortie de md() (déjà échappée).
export function rendreMd(el, texte, ctx) { el.innerHTML = md(texte, ctx); return el; }
