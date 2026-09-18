/* ── 诗词格律校验器 · 前端 ────────────────────────────────────
   纯原生 JS，无构建步骤。所有判定都来自后端 /api/check，
   前端只管把结果画出来。
   ─────────────────────────────────────────────────────────── */

(() => {
  'use strict';

  // ── 元素 ──────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const textarea = $('text');
  const bookSel = $('book');
  const shapeSel = $('shape');
  const sampleSel = $('samples');
  const runBtn = $('run');
  const clearBtn = $('clear');
  const resultPane = $('result');
  const metaEl = $('meta');
  const tip = $('tooltip');
  const toastEl = $('toast');

  let META = null;

  // ── 示例 ──────────────────────────────────────────────
  const SAMPLES = {
    '五言绝句 · 登鹳雀楼': '登鹳雀楼\n\n白日依山尽，黄河入海流。\n欲穷千里目，更上一层楼。',
    '五言律诗 · 春望': '春望\n\n国破山河在，城春草木深。\n感时花溅泪，恨别鸟惊心。\n烽火连三月，家书抵万金。\n白头搔更短，浑欲不胜簪。',
    '七言律诗 · 闻官军收河南河北': '闻官军收河南河北\n\n剑外忽传收蓟北，初闻涕泪满衣裳。\n却看妻子愁何在，漫卷诗书喜欲狂。\n白日放歌须纵酒，青春作伴好还乡。\n即从巴峡穿巫峡，便下襄阳向洛阳。',
    '词 · 水调歌头': '《水调歌头·明月几时有》\n\n明月几时有，把酒问青天。不知天上宫阙，今夕是何年。\n我欲乘风归去，又恐琼楼玉宇，高处不胜寒。起舞弄清影，何似在人间。\n\n转朱阁，低绮户，照无眠。不应有恨，何事长向别时圆。\n人有悲欢离合，月有阴晴圆缺，此事古难全。但愿人长久，千里共婵娟。',
    '词 · 浣溪沙': '《浣溪沙》\n\n一曲新词酒一杯，去年天气旧亭台。夕阳西下几时回。\n无可奈何花落去，似曾相识燕归来。小园香径独徘徊。',
    '仄韵变体 · 江雪': '江雪\n\n千山鸟飞绝，万径人踪灭。\n孤舟蓑笠翁，独钓寒江雪。',
    '故意写错 · 待改': '落叶随风起\n寒窗一夜愁\n故人音信绝\n独对孤灯寒',
  };

  // ── 工具 ──────────────────────────────────────────────
  const el = (tag, cls, text) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  };

  const tipLines = (lines) => lines.filter(Boolean).join('\n');

  let toastTimer = null;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 2600);
  }

  // ── tooltip ───────────────────────────────────────────
  function showTip(text, ev) {
    tip.textContent = text;
    tip.style.whiteSpace = 'pre-line';
    tip.hidden = false;
    moveTip(ev);
  }
  function moveTip(ev) {
    const pad = 14;
    const rect = tip.getBoundingClientRect();
    let x = ev.clientX + pad;
    let y = ev.clientY + pad;
    if (x + rect.width > innerWidth - 8) x = ev.clientX - rect.width - pad;
    if (y + rect.height > innerHeight - 8) y = ev.clientY - rect.height - pad;
    tip.style.left = Math.max(8, x) + 'px';
    tip.style.top = Math.max(8, y) + 'px';
  }
  function hideTip() { tip.hidden = true; }

  document.addEventListener('mouseover', (e) => {
    const t = e.target.closest('[data-tip]');
    if (t) showTip(t.dataset.tip, e);
  });
  document.addEventListener('mousemove', (e) => {
    if (!tip.hidden) moveTip(e);
  });
  document.addEventListener('mouseout', (e) => {
    if (!e.target.closest('[data-tip]')) return;
    // 从一个带提示的字移到另一个带提示的字时不要闪烁
    const next = e.relatedTarget;
    if (next && next.closest && next.closest('[data-tip]')) return;
    hideTip();
  });
  document.addEventListener('scroll', hideTip, true);

  // ── 后端调用 ──────────────────────────────────────────
  async function api(path, options) {
    const res = await fetch(path, options);
    let data;
    try {
      data = await res.json();
    } catch (_) {
      throw new Error(`服务返回了非 JSON 内容（HTTP ${res.status}）`);
    }
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || `HTTP ${res.status}`);
    }
    return data;
  }

  async function loadMeta() {
    try {
      META = await api('/api/meta');
    } catch (err) {
      metaEl.textContent = '无法连接服务：' + err.message;
      return;
    }
    bookSel.innerHTML = '';
    for (const name of META.books) {
      const info = META.books_info[name] || {};
      const opt = el('option', null, name);
      opt.value = name;
      if (name === '中华新韵' && !info.available) {
        opt.disabled = true;
        opt.textContent = name + '（未安装 pypinyin）';
      }
      bookSel.appendChild(opt);
    }
    metaEl.innerHTML =
      `v${META.version} · 平水韵 <b>${META.books_info['平水韵'].chars}</b> 字 · ` +
      `词牌 <b>${META.cipai_count}</b> 个`;
  }

  // ── 校验 ──────────────────────────────────────────────
  async function run() {
    const text = textarea.value.trim();
    if (!text) { toast('请先粘贴诗稿'); textarea.focus(); return; }

    runBtn.disabled = true;
    runBtn.textContent = '校验中…';
    try {
      const data = await api('/api/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          book: bookSel.value || '平水韵',
          shape: shapeSel.value || 'auto',
        }),
      });
      render(data.result);
    } catch (err) {
      renderError(err.message);
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = '校 验';
    }
  }

  // ── 渲染：骨架 ────────────────────────────────────────
  function render(result) {
    resultPane.innerHTML = '';
    const wrap = el('div', 'report');

    if (result.kind === '未知') {
      wrap.appendChild(unknownCard(result));
      resultPane.appendChild(wrap);
      return;
    }

    const isCi = result.kind === '词';
    const obj = isCi ? result.ci : result.poem;

    wrap.appendChild(verdictCard(obj, result));
    wrap.appendChild(infoGrid(obj, result, isCi));
    wrap.appendChild(verseSection(obj, isCi));
    if (isCi && obj.break_segments && obj.break_segments.length) {
      wrap.appendChild(breakSection(obj));
    }
    wrap.appendChild(violationSection(obj, isCi));
    wrap.appendChild(rhymeSection(obj, isCi));
    if (!isCi) wrap.appendChild(coupletSection(obj));
    if (isCi && obj.hints && obj.hints.length) wrap.appendChild(hintSection(obj));
    wrap.appendChild(issueSection(obj));

    resultPane.appendChild(wrap);
    resultPane.scrollTop = 0;
  }

  function renderError(msg) {
    resultPane.innerHTML = '';
    const wrap = el('div', 'report');
    const card = el('div', 'verdict-card bad');
    card.appendChild(el('div', 'verdict-word', '校验失败'));
    wrap.appendChild(card);
    const list = el('div', 'list');
    const item = el('div', 'item level-错误');
    item.appendChild(el('span', 'ico', '✘'));
    const body = el('div');
    body.appendChild(el('span', 'title', '错误'));
    body.appendChild(el('span', 'body', msg));
    item.appendChild(body);
    list.appendChild(item);
    wrap.appendChild(list);
    resultPane.appendChild(wrap);
  }

  function unknownCard(result) {
    const wrap = el('div');
    const card = el('div', 'verdict-card mid');
    const left = el('div', 'verdict-left');
    left.appendChild(el('div', 'verdict-word', '无法识别体裁'));
    card.appendChild(left);
    wrap.appendChild(card);

    const sec = el('div', 'section');
    sec.appendChild(el('h3', null, '说明'));
    const list = el('div', 'list');
    const item = el('div', 'item level-提示');
    item.appendChild(el('span', 'ico', '·'));
    const body = el('div');
    (result.message || '').split('\n').forEach((line) => {
      body.appendChild(el('div', 'body', line));
    });
    item.appendChild(body);
    list.appendChild(item);
    sec.appendChild(list);
    wrap.appendChild(sec);
    return wrap;
  }

  // ── 渲染：结论卡 ──────────────────────────────────────
  function verdictCard(obj, result) {
    const v = obj.verdict || '';
    const cls = /合律|合谱/.test(v) ? 'good' : (/变体/.test(v) ? 'mid' : 'bad');
    const card = el('div', 'verdict-card ' + cls);

    const left = el('div', 'verdict-left');
    left.appendChild(el('div', 'verdict-word', v));
    left.appendChild(el('div', 'verdict-tag', result.kind));

    const right = el('div', 'score-wrap');
    const bar = el('div', 'score-bar');
    const pct = Math.round((obj.score || 0) * 100);
    const fill = el('div', 'score-fill');
    fill.style.width = pct + '%';
    bar.appendChild(fill);
    right.appendChild(bar);
    right.appendChild(el('div', 'score-num', pct + '%'));
    right.appendChild(el('div', 'verdict-tag', '平仄符合度'));

    card.appendChild(left);
    card.appendChild(right);
    return card;
  }

  // ── 渲染：基本信息 ────────────────────────────────────
  function infoGrid(obj, result, isCi) {
    const grid = el('div', 'info-grid');
    const add = (k, v) => {
      if (v == null || v === '') return;
      const item = el('div', 'info-item');
      item.appendChild(el('span', 'k', k));
      item.appendChild(el('span', 'v', v));
      grid.appendChild(item);
    };

    if (obj.title) add('标题', obj.title);
    if (isCi) {
      add('词牌', obj.cipai);
      if (obj.aliases && obj.aliases.length) add('别名', obj.aliases.join('、'));
      add('韵书', obj.book);
      add('段数', obj.spec && obj.spec['段数']);
      add('句数', obj.clauses.length);
      add('字数', `${obj.actual_chars} / ${obj.expected_chars}` +
        (obj.actual_chars === obj.expected_chars ? '  ✔' : '  ✘'));

      // 句读骨架（skeleton 也是 @property，前端自行拼）
      const sk = obj.clauses.map((c) => c.pattern.length).join('·');
      const row = el('div', 'info-item');
      row.style.gridColumn = '1 / -1';
      row.appendChild(el('span', 'k', '句读骨架'));
      row.appendChild(el('span', 'v skeleton', sk));
      grid.appendChild(row);
    } else {
      add('体裁', obj.genre);
      add('格式', obj.pattern_label);
      add('韵书', obj.book);
      add('句数', obj.clauses.length);
      if (obj.shape_note) add('说明', obj.shape_note);
    }

    // 符合度只统计韵书查得到的字：查不到的字既不进分子也不进分母，
    // 所以一首诗可能显示 100%，却有一半的字根本没查过。把覆盖率摆出来。
    const cov = result.coverage || {};
    const total = cov.total || 0;
    const known = cov.known || 0;
    if (total) {
      const miss = total - known;
      const row = el('div', 'info-item');
      row.style.gridColumn = '1 / -1';
      row.appendChild(el('span', 'k', '已判定字数'));
      row.appendChild(
        el('span', 'v' + (miss ? ' cov-warn' : ''), miss
          ? `${known} / ${total}（另有 ${miss} 字韵书未收录或句式不符，未计入符合度）`
          : `${known} / ${total}（全部字均已判定）`)
      );
      grid.appendChild(row);
    }
    return grid;
  }

  // ── 渲染：逐句对照 ────────────────────────────────────
  function clauseChars(c, isCi) {
    return isCi ? ((c.result && c.result.chars) || []) : (c.chars || []);
  }
  function clauseIssues(c, isCi) {
    return isCi ? ((c.result && c.result.issues) || []) : (c.issues || []);
  }
  function clausePattern(c, isCi) {
    return isCi ? c.raw_pattern : c.pattern;
  }

  function charSpan(ch) {
    const span = el('span', 'ch ' + charClass(ch), ch.char);
    span.dataset.tip = tipLines([
      `字：${ch.char}`,
      ch.expected === '中' ? '定式：此处平仄不拘'
        : (ch.expected ? `定式要求：${ch.expected}` : ''),
      `韵书读作：${(ch.tones || []).join(' / ') || '未收录'}`,
      ch.status && ch.status !== '合律' ? `判定：${ch.status}` : '',
    ]);
    return span;
  }

  function charClass(ch) {
    if (ch.status === '出律') return 'ch-violation';
    if (ch.chosen === '平') return 'ch-ping';
    if (ch.chosen === '仄') return 'ch-ze';
    return 'ch-unknown';
  }

  function verseSection(obj, isCi) {
    const sec = el('div', 'section');
    sec.appendChild(el('h3', null, isCi ? '逐 句 对 照' : '平 仄 谱 对 照'));

    obj.clauses.forEach((c) => {
      const chars = clauseChars(c, isCi);
      const issues = clauseIssues(c, isCi);
      const pattern = clausePattern(c, isCi);

      const row = el('div', 'verse');
      row.appendChild(el('div', 'verse-no', String(c.index + 1)));

      const charsBox = el('div', 'verse-chars');
      if (chars.length) {
        chars.forEach((ch) => charsBox.appendChild(charSpan(ch)));
      } else {
        charsBox.textContent = c.text || '';
      }
      row.appendChild(charsBox);

      row.appendChild(el('div', 'verse-pattern', pattern || ''));

      const tail = el('div', 'verse-tail');
      // 注意：词的 is_rhyme 是 Python 的 @property，不会被序列化，
      // 因此这里必须读 rhyme_flag（0=不押韵，1/2/3/4 = 韵/叠韵/换韵/叶韵）。
      if (isCi) {
        if (c.rhyme_flag) {
          const map = { 1: '韵', 2: '叠韵', 3: '换韵', 4: '叶韵' };
          tail.appendChild(el('span', 'badge rhyme', map[c.rhyme_flag] || '韵'));
        }
      } else if (c.is_rhyme) {
        tail.appendChild(el('span', 'badge rhyme', '韵'));
      }
      issues.filter((i) => i.level !== '错误' && i.title !== '字数不符')
        .forEach((i) => tail.appendChild(el('span', 'badge note', i.title)));

      const sizeOk = isCi ? (chars.length === pattern.replace(/[^平仄中]/g, '').length && chars.length > 0)
        : (chars.length === (pattern || '').length);
      const hasErr = issues.some((i) => i.level === '错误');
      const ok = sizeOk && !hasErr && !chars.some((x) => x.status === '出律');
      tail.appendChild(el('span', ok ? 'mark-ok' : 'mark-bad', ok ? '✔' : '✘'));

      row.appendChild(tail);
      sec.appendChild(row);
    });
    return sec;
  }

  // ── 渲染：句读对照 ────────────────────────────────────
  function breakSection(obj) {
    const sec = el('div', 'section');
    sec.appendChild(el('h3', null, '句 读 对 照'));

    obj.break_segments.forEach((seg) => {
      const box = el('div', 'jp-block');

      const needRow = el('div', 'jp-row');
      needRow.appendChild(el('span', 'k', '词谱要求'));
      const nv = el('span', 'v');
      seg.required.forEach((p, i) => {
        if (i) nv.appendChild(el('span', 'sep', '｜'));
        const span = el('span', null, `${seg.indices[i] + 1} 句 `);
        const cnt = el('span', 'cnt', `${p.length} 字`);
        span.appendChild(cnt);
        nv.appendChild(span);
      });
      needRow.appendChild(nv);
      box.appendChild(needRow);

      const mineRow = el('div', 'jp-row');
      mineRow.appendChild(el('span', 'k', '你的断句'));
      const mv = el('span', 'v');
      seg.actual.forEach((t, i) => {
        if (i) mv.appendChild(el('span', 'sep', '｜'));
        mv.appendChild(el('span', null, t));
        mv.appendChild(el('span', 'cnt', `（${t.length}字）`));
      });
      mineRow.appendChild(mv);
      box.appendChild(mineRow);

      const fixRow = el('div', 'jp-row');
      fixRow.appendChild(el('span', 'k', '按谱重断'));
      const fv = el('span', 'v');
      seg.rebuilt.forEach((t, i) => {
        if (i) fv.appendChild(el('span', 'sep', '｜'));
        fv.appendChild(el('span', null, t));
      });
      fixRow.appendChild(fv);
      box.appendChild(fixRow);

      const verdict = el('div', 'jp-verdict ' + (seg.fixable ? 'good' : 'bad'));
      verdict.textContent = seg.fixable
        ? '↑ 按谱重断后平仄全合 → 用字没问题，只是「逗」的位置不对，照上面重断即可（语义请自行核对）'
        : `↑ 按谱重断后仍有出律：${(seg.bad || []).join('、')} —— 不只是逗号问题，需调整用字`;
      box.appendChild(verdict);

      sec.appendChild(box);
    });
    return sec;
  }

  // ── 渲染：出律清单 ────────────────────────────────────
  function collectProblems(obj, isCi) {
    const viol = [], unknown = [], serious = [];
    obj.clauses.forEach((c) => {
      clauseChars(c, isCi).forEach((x) => {
        if (x.status === '出律') viol.push([c.index, x]);
        else if (x.status === '未收录') unknown.push([c.index, x]);
      });
      clauseIssues(c, isCi).forEach((i) => {
        if (i.level === '错误') serious.push([c.index, i]);
      });
    });
    (obj.issues || []).forEach((i) => {
      if (i.level === '错误') serious.push([null, i]);
    });
    return { viol, unknown, serious };
  }

  function violationSection(obj, isCi) {
    const sec = el('div', 'section');
    sec.appendChild(el('h3', null, '出 律 清 单'));
    const { viol, serious } = collectProblems(obj, isCi);
    const list = el('div', 'list');

    if (!viol.length && !serious.length) {
      const item = el('div', 'item level-建议');
      item.appendChild(el('span', 'ico', '✔'));
      const body = el('div');
      body.appendChild(el('span', 'body', isCi ? '无出律，全部合谱。' : '无出律，全部合律。'));
      item.appendChild(body);
      list.appendChild(item);
    } else {
      viol.forEach(([idx, ch]) => {
        const item = el('div', 'item level-错误');
        item.appendChild(el('span', 'ico', '✘'));
        const body = el('div');
        body.appendChild(el('span', 'title', `第 ${idx + 1} 句第 ${ch.index + 1} 字`));
        const txt = el('span', 'body');
        txt.appendChild(el('em', null, `「${ch.char}」`));
        txt.appendChild(document.createTextNode(
          `定式要求 ${ch.expected || '—'}，该字读作 ${(ch.tones || []).join('/') || '未知'}`
        ));
        body.appendChild(txt);
        item.appendChild(body);
        list.appendChild(item);
      });
      const seen = new Set();
      serious.forEach(([idx, i]) => {
        const key = `${idx}-${i.title}-${i.detail}`;
        if (seen.has(key)) return;
        seen.add(key);
        const item = el('div', 'item level-' + (i.level || '错误'));
        item.appendChild(el('span', 'ico', '✘'));
        const body = el('div');
        body.appendChild(el('span', 'title',
          (idx == null ? '' : `第 ${idx + 1} 句 · `) + i.title));
        body.appendChild(el('span', 'body', i.detail));
        item.appendChild(body);
        list.appendChild(item);
      });
    }
    sec.appendChild(list);
    return sec;
  }

  // ── 渲染：押韵 ────────────────────────────────────────
  function rhymeSection(obj, isCi) {
    const sec = el('div', 'section');
    sec.appendChild(el('h3', null, isCi ? '押 韵 分 析' : '押 韵 分 析'));
    if (isCi) {
      (obj.rhyme_groups || []).forEach((g) => {
        const box = el('div', 'rhyme-group');
        const head = el('div', 'grp-head');
        head.appendChild(el('span', 'no', `韵组 ${g.group_id}`));
        head.appendChild(el('span', 'badge note', g.expected_tone === '中' ? '平仄不拘' : `应押${g.expected_tone}声`));
        const chars = el('span', 'feet-chars', (g.feet || []).map((f) => f[1]).join(' '));
        head.appendChild(chars);
        head.appendChild(el('span', g.ok ? 'mark-ok' : 'mark-bad', g.ok ? '✔' : '✘'));
        if (g.main_group) head.appendChild(el('span', 'badge note', g.main_group));
        box.appendChild(head);
        (g.notes || []).forEach((n) => box.appendChild(el('div', 'grp-note', '⚠ ' + n)));
        sec.appendChild(box);
      });
      if (!(obj.rhyme_groups || []).length) {
        sec.appendChild(el('div', 'empty-line', '该词牌没有押韵要求。'));
      }
    } else {
      const r = obj.rhyme;
      if (!r) { sec.appendChild(el('div', 'empty-line', '无押韵信息。')); return sec; }
      if (r.main_group) {
        const p = el('div', 'info-item');
        p.style.marginBottom = '8px';
        p.appendChild(el('span', 'k', '主韵'));
        p.appendChild(el('span', 'v', `${r.book} ${r.main_group}`));
        sec.appendChild(p);
      }
      const table = el('table', 'feet');
      const thead = el('tr');
      ['句', '韵脚', '韵部', '', ''].forEach((t) => thead.appendChild(el('th', null, t)));
      table.appendChild(thead);
      (r.feet || []).forEach((f) => {
        const tr = el('tr', f.ok ? '' : 'bad');
        tr.appendChild(el('td', null, String(f.clause_index + 1)));
        tr.appendChild(el('td', 'char', f.char));
        tr.appendChild(el('td', null, (f.groups || []).join('／') || '未收录'));
        tr.appendChild(el('td', null, f.is_first ? '首句（可借邻韵）' : ''));
        const markTd = el('td');
        markTd.appendChild(el('span', f.ok ? 'mark-ok' : 'mark-bad', f.ok ? '✔' : '✘'));
        if (f.note) markTd.appendChild(el('span', 'badge note', f.note));
        tr.appendChild(markTd);
        table.appendChild(tr);
      });
      sec.appendChild(table);
      (r.notes || []).forEach((n) => {
        const item = el('div', 'item level-警告');
        item.style.marginTop = '8px';
        item.appendChild(el('span', 'ico', '⚠'));
        const b = el('div');
        b.appendChild(el('span', 'body', n));
        item.appendChild(b);
        sec.appendChild(item);
      });
    }
    return sec;
  }

  // ── 渲染：对仗 ────────────────────────────────────────
  function coupletSection(obj) {
    const sec = el('div', 'section');
    sec.appendChild(el('h3', null, '对 仗 分 析（仅供参考）'));

    (obj.couplets || []).forEach((cp) => {
      const box = el('div', 'couplet');
      const head = el('div', 'couplet-head');
      head.appendChild(el('span', 'label', cp.label));
      head.appendChild(el('span', 'badge note',
        `第 ${cp.left_index + 1}、${cp.right_index + 1} 句`));
      head.appendChild(el('span', 'badge ' + (cp.required ? 'rhyme' : 'note'),
        cp.required ? '必对' : '可不对'));

      const d = cp.detail;
      if (!d) {
        head.appendChild(el('span', 'badge note', '字数不等，无法比较'));
        box.appendChild(head);
        sec.appendChild(box);
        return;
      }
      const good = d.verdict === '工对' || d.verdict === '宽对';
      head.appendChild(el('span', good ? 'mark-ok' : 'mark-bad', d.verdict));
      box.appendChild(head);

      (d.segments || []).forEach((s) => {
        const shared = (s.left_cats || []).filter((c) => (s.right_cats || []).includes(c));
        const row = el('div', 'seg-row ' + (shared.length ? 'hit' : 'miss'));
        row.appendChild(el('span', 'marker', shared.length ? '○' : '×'));
        row.appendChild(el('span', 'word', s.left));
        row.appendChild(el('span', 'cats', (s.left_cats || []).join('/') || '（未归类）'));
        row.appendChild(el('span', 'arrow', '—'));
        row.appendChild(el('span', 'word', s.right));
        row.appendChild(el('span', 'cats', (s.right_cats || []).join('/') || '（未归类）'));
        box.appendChild(row);
      });

      if (d.notes && d.notes.length) {
        const notes = el('div', 'notes');
        d.notes.forEach((n) => notes.appendChild(el('div', null, '· ' + n)));
        box.appendChild(notes);
      }
      sec.appendChild(box);
    });
    return sec;
  }

  // ── 渲染：对仗提示（词）──────────────────────────────
  function hintSection(obj) {
    const sec = el('div', 'section');
    sec.appendChild(el('h3', null, '对 仗 提 示'));
    const list = el('div', 'list');
    (obj.hints || []).forEach((h) => {
      const item = el('div', 'item level-提示');
      item.appendChild(el('span', 'ico', '·'));
      const b = el('div');
      b.appendChild(el('span', 'body', h));
      item.appendChild(b);
      list.appendChild(item);
    });
    list.appendChild(el('div', 'empty-line', '词的对仗较自由，不忌重字，是否用对仗由作者决定。'));
    sec.appendChild(list);
    return sec;
  }

  // ── 渲染：提示与建议 ──────────────────────────────────
  function issueSection(obj) {
    const issues = (obj.issues || []).filter((i) => i.level !== '错误');
    const sec = el('div', 'section');
    sec.appendChild(el('h3', null, '提 示 与 建 议'));
    const list = el('div', 'list');

    issues.forEach((i) => {
      const item = el('div', 'item level-' + i.level);
      item.appendChild(el('span', 'ico', i.level === '建议' ? '→' : '·'));
      const b = el('div');
      b.appendChild(el('span', 'title', i.title));
      b.appendChild(el('span', 'body', i.detail));
      item.appendChild(b);
      list.appendChild(item);
    });

    // 未收录字
    const { unknown } = collectProblems(obj, obj.kind === '词');
    if (unknown.length) {
      const chars = [...new Set(unknown.map(([, c]) => c.char))].join('');
      const item = el('div', 'item level-提示');
      item.appendChild(el('span', 'ico', '·'));
      const b = el('div');
      b.appendChild(el('span', 'title', '韵书未收录'));
      b.appendChild(el('span', 'body',
        `以下字不在韵书数据中，未参与平仄判定：${chars}。可补录到 知识库/韵书/。`));
      item.appendChild(b);
      list.appendChild(item);
    }

    if (!list.children.length) {
      list.appendChild(el('div', 'empty-line', '无。'));
    }
    sec.appendChild(list);

    const foot = el('div', 'empty-line');
    foot.style.marginTop = '10px';
    foot.textContent = '本工具为格律辅助，不代替作者判断；意境、修辞请自行斟酌。';
    sec.appendChild(foot);
    return sec;
  }

  // ── 事件 ──────────────────────────────────────────────
  runBtn.addEventListener('click', run);
  clearBtn.addEventListener('click', () => {
    textarea.value = '';
    textarea.focus();
    resultPane.innerHTML = '';
    const empty = el('div', 'empty');
    empty.appendChild(el('div', 'empty-mark', '平 仄'));
    empty.appendChild(el('p', null, '左侧粘贴诗稿，点「校 验」'));
    empty.appendChild(el('p', 'dim', '报告会指出出律位置、韵部归属与修改建议'));
    resultPane.appendChild(empty);
  });

  sampleSel.addEventListener('change', () => {
    const key = sampleSel.value;
    if (!key) return;
    textarea.value = SAMPLES[key] || '';
    sampleSel.value = '';
    run();
  });

  textarea.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      run();
    }
  });

  // 初始化
  (function init() {
    for (const name of Object.keys(SAMPLES)) {
      const opt = el('option', null, name);
      opt.value = name;
      sampleSel.appendChild(opt);
    }
    loadMeta();
  })();
})();
