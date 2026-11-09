'use strict';
const report = JSON.parse(document.getElementById('report-data').textContent);
const groups = report.blocks;
const state = {group: groups[0]?.id ?? null, filter: 'all', expanded: null};
const $ = id => document.getElementById(id);
const type = s => s === 'USER_SPECIFIED' ? 'user' : s === 'AI_SUPPLEMENTED' ? 'ai' : 'unknown';
const icon = s => s === 'user' ? '♙' : s === 'ai' ? '✧' : '?';
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function button(className, text, action) {
  const node = el('button', className, text); node.type = 'button';
  node.addEventListener('click', action); return node;
}
function card(item) {
  const open = state.expanded === item.id, category = type(item.source_class);
  const article = el('article', 'card' + (open ? ' expanded' : ''));
  const toggle = button('card-toggle', undefined, () => { state.expanded = open ? null : item.id; render(); });
  toggle.setAttribute('aria-expanded', String(open));
  const head = el('div', 'card-head'), dot = el('span', 'dot ' + category, icon(category)); dot.setAttribute('aria-hidden', 'true');
  const copy = el('div', 'card-copy'); copy.append(el('div', 'card-name', item.title), el('div', 'card-origin ' + category, item.label));
  if (item.impact_level === 'HIGH') copy.append(el('span', 'impact-label', '重要影响'));
  head.append(dot, copy, el('span', 'arrow', open ? '⌃' : '⌄'));
  toggle.append(head, el('p', 'card-reason', item.reason)); article.append(toggle);
  if (open) {
    const region = el('div', 'expanded-region');
    for (const [label, value] of [['对使用体验的影响', item.impact], [item.detail_label, item.detail]]) {
      if (!value) continue;
      const section = el('div'); section.append(el('div', 'detail-label', label), el('div', 'detail-text', value)); region.append(section);
    }
    article.append(region);
  }
  return article;
}
function render() {
  $('project-title').textContent = report.title;
  $('gap-summary').textContent = report.gap_summary; $('gap-summary').hidden = !report.gap_summary;
  const totals = [['user', 'USER_SPECIFIED', '用户要求 / 确认'], ['ai', 'AI_SUPPLEMENTED', 'AI 自主选择'], ['unknown', 'UNKNOWN', '来源未确定']];
  $('summary').replaceChildren(...totals.map(([category, key, label]) => {
    const node = el('span', 'summary-item'); node.append(el('span', 'dot ' + category, icon(category)), el('strong', '', report.counts[key]), el('span', '', label)); return node;
  }));
  $('nav').replaceChildren(...groups.map(group => {
    const nav = button('nav-button', undefined, () => { state.group = group.id; state.expanded = null; render(); });
    nav.setAttribute('aria-current', String(group.id === state.group));
    const text = el('span', 'nav-text'); text.append(el('span', 'nav-title', group.name), el('span', 'nav-sub', group.decisions.length + ' 项决定' + (group.ordinary_changes.length ? ' · 含其他调整' : '')));
    nav.append(el('span', 'nav-symbol', '▤'), text); return nav;
  }));
  $('mobile-select').replaceChildren(...groups.map(group => {
    const opt = el('option', '', group.name); opt.value = group.id; opt.selected = group.id === state.group; return opt;
  }));
  const group = groups.find(g => g.id === state.group);
  $('group-title').textContent = group?.name ?? '本次实现审阅';
  $('group-subtitle').textContent = '本次开发新增或改变的重要决定';
  const shown = group?.decisions.filter(d => state.filter === 'all' || type(d.source_class) === state.filter) ?? [];
  $('count').textContent = shown.length + ' 项决定';
  $('filters').replaceChildren(...[['all', '全部'], ['ai', 'AI'], ['user', '用户'], ['unknown', '未确定']].map(([key, label]) => {
    const filter = button('filter', label, () => { state.filter = key; state.expanded = null; render(); }); filter.setAttribute('aria-pressed', String(key === state.filter)); return filter;
  }));
  $('cards').replaceChildren(...shown.map(card));
  if (!shown.length) $('cards').append(el('div', 'empty', '此功能下没有符合筛选条件的重要决定'));
  if (state.filter === 'all' && group?.ordinary_changes.length) {
    const ordinary = el('details', 'ordinary'); ordinary.append(el('summary', '', '其他调整 · ' + group.ordinary_changes.length + ' 组'));
    for (const change of group.ordinary_changes) {
      const section = el('div', 'ordinary-section'); section.append(el('div', 'detail-label', change.category), el('div', 'detail-text', change.summaries.join('；')));
      if (change.exclusions.length) section.append(el('p', 'detail-text', '排除说明：' + change.exclusions.join('；')));
      ordinary.append(section);
    }
    $('cards').append(ordinary);
  }
  $('report-meta').textContent = '任务 ' + report.task_id + ' · 生成于 ' + report.generated_at + ' · 检查范围：' + report.scope.join('、') + '。可凭任务编号和功能名称查询具体改动。' + (report.excluded_path_count ? '已按规则排除 ' + report.excluded_path_count + ' 个私密或生成路径。' : '') + report.limitation;
}
$('mobile-select').addEventListener('change', e => { state.group = e.target.value; state.expanded = null; render(); });
render();
