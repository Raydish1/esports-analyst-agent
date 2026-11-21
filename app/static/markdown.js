// A small markdown renderer for the agent's answers: headings, paragraphs, lists, tables, bold, italics, code and
// links. It builds DOM nodes with textContent only, never innerHTML, so nothing in an answer can become markup.

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)\s]+\))/;

export function inline(parent, text) {
  for (const part of text.split(INLINE)) {
    if (!part) continue;
    let node;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      node = document.createElement("strong");
      inline(node, part.slice(2, -2));
    } else if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      node = document.createElement("code");
      node.textContent = part.slice(1, -1);
    } else if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      node = document.createElement("em");
      inline(node, part.slice(1, -1));
    } else if (part.startsWith("[") && part.includes("](")) {
      const [, label, url] = part.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/) || [];
      if (label && /^https?:\/\//i.test(url)) {
        node = document.createElement("a");
        node.href = url;
        node.target = "_blank";
        node.rel = "noopener noreferrer";
        node.textContent = label;
      }
    }
    parent.append(node || document.createTextNode(part));
  }
  return parent;
}

const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
const isRule = (line) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
const LIST = /^(\s*)([-*+]|\d+[.)])\s+(.*)$/;

export function render(text) {
  const root = document.createElement("div");
  root.className = "md";
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  let paragraph = [];
  const flush = () => {
    if (paragraph.length) {
      const p = document.createElement("p");
      paragraph.forEach((line, n) => {
        if (n) p.append(document.createElement("br"));
        inline(p, line.trim());
      });
      root.append(p);
      paragraph = [];
    }
  };
  while (i < lines.length) {
    const line = lines[i];
    const heading = line.match(/^\s*(#{1,4})\s+(.*)$/);
    if (!line.trim()) {
      flush();
      i++;
    } else if (heading) {
      flush();
      const h = document.createElement(`h${Math.min(6, heading[1].length + 2)}`);
      root.append(inline(h, heading[2]));
      i++;
    } else if (/^\s*([-*_])\1{2,}\s*$/.test(line)) {
      flush();
      root.append(document.createElement("hr"));
      i++;
    } else if (line.trim().startsWith("|") && i + 1 < lines.length && isRule(lines[i + 1])) {
      flush();
      const wrap = document.createElement("div");
      wrap.className = "table-wrap";
      const table = document.createElement("table");
      const head = table.createTHead().insertRow();
      for (const c of cells(line)) inline(head.appendChild(document.createElement("th")), c);
      const body = table.createTBody();
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        const row = body.insertRow();
        for (const c of cells(lines[i])) inline(row.insertCell(), c);
        i++;
      }
      wrap.append(table);
      root.append(wrap);
    } else if (LIST.test(line)) {
      flush();
      const ordered = /\d/.test(line.match(LIST)[2]);
      const list = document.createElement(ordered ? "ol" : "ul");
      if (ordered) list.start = parseInt(line.match(LIST)[2], 10);  // a list that starts at 5 shows 5
      // A blank line between items doesn't end the list: answers often write "1. ..., an indented "- ...", a blank
      // line, then 2. ...", and ending it there restarted every item at 1. It goes on to an indented line or an item
      // of the same kind (numbered or not), and ends at anything else.
      const continues = (j) => {
        while (j < lines.length && !lines[j].trim()) j++;
        if (j >= lines.length) return -1;
        const m = lines[j].match(LIST);
        if (/^\s{2,}/.test(lines[j]) || (m && /\d/.test(m[2]) === ordered)) return j;
        return -1;
      };
      while (i < lines.length) {
        if (!lines[i].trim()) {
          const next = continues(i);
          if (next < 0) break;
          i = next;
          continue;
        }
        if (!LIST.test(lines[i]) && !/^\s{2,}/.test(lines[i])) break;
        const m = lines[i].match(LIST);
        if (m && m[1].length >= 2 && list.lastChild) {  // indented: a list inside the last item
          const tag = /\d/.test(m[2]) ? "OL" : "UL";
          let sub = list.lastChild.lastElementChild;
          if (!sub || sub.tagName !== tag) sub = list.lastChild.appendChild(document.createElement(tag));
          sub.append(inline(document.createElement("li"), m[3]));
        } else if (m) {
          list.append(inline(document.createElement("li"), m[3]));
        } else if (list.lastChild) {
          list.lastChild.append(document.createElement("br"));
          inline(list.lastChild, lines[i].trim());
        }
        i++;
      }
      root.append(list);
    } else {
      paragraph.push(line);
      i++;
    }
  }
  flush();
  return root;
}
