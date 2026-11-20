'use strict';
const escapeHtml = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sourceBlock = keys => `<div class="source"><span class="source-pill">SOURCE CONNECTION</span>${keys.map(key => {
  const s = sourceMap.entries[key];
  if (!s) throw new Error(`Unknown source connection: ${key}`);
  return `<details><summary>${escapeHtml(s.file)}${s.name ? ` · ${escapeHtml(s.name)}` : ''}</summary><p><a href="${s.url}">View the version used for this derivation, line ${s.line}</a></p><pre><code>${escapeHtml(s.code)}</code></pre></details>`;
}).join('')}<span>Source snapshot ${sourceMap.revision.slice(0, 10)} · regenerate with tools/build_derivation_sources.py</span></div>`;
const blockMath = text => text.replace(/\$\$([\s\S]*?)\$\$/g, (_, tex) => `<div class="equation">$$${escapeHtml(tex)}$$</div>`);
document.getElementById('navigation').innerHTML = chapters.map((c,i)=>`<a href="#${c.id}"><span>${c.number || String(i+1).padStart(2,'0')}</span>${c.title}</a>`).join('');
document.getElementById('chapters').innerHTML = chapters.map((c,i)=>`<section id="${c.id}"><div class="chapter-heading"><span class="chapter-number">${c.number || String(i+1).padStart(2,'0')}</span><div><h2>${c.title}</h2><p>${c.subtitle}</p></div></div><div class="card">${blockMath(c.html)}${sourceBlock(c.sources)}</div></section>`).join('');
const mathErrors = [];
if (typeof renderMathInElement === 'function') {
  renderMathInElement(document.body, {delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],macros:{'\\frac':'\\dfrac'},throwOnError:false,errorCallback:message=>mathErrors.push(message)});
  document.querySelectorAll('.hero-equation .math').forEach(el=>katex.render(el.textContent,el,{throwOnError:false}));
} else {
  document.getElementById('chapters').insertAdjacentHTML('afterbegin','<p class="error">Math rendering could not load. Reload the page; the renderer is included in docs/vendor/katex.</p>');
}
window.derivationMathErrors = mathErrors;
const navLinks = Array.from(document.querySelectorAll('nav a'));
const setActive = id => navLinks.forEach(a=>a.hash===`#${id}` ? a.setAttribute('aria-current','location') : a.removeAttribute('aria-current'));
const sections = Array.from(document.querySelectorAll('main section'));
let pendingScroll = false;
function updateNavigation() {
  pendingScroll = false;
  const threshold = 130;
  let active = sections[0].id;
  for (const section of sections) if(section.getBoundingClientRect().top <= threshold) active=section.id;
  setActive(active);
}
window.addEventListener('scroll',()=>{if(!pendingScroll){pendingScroll=true;requestAnimationFrame(updateNavigation)}},{passive:true});
updateNavigation();
document.getElementById('print').addEventListener('click',()=>{
  const details = [...document.querySelectorAll('.card>details')];
  const states = details.map(d=>d.open);
  details.forEach(d=>d.open=true);
  window.print();
  details.forEach((d,i)=>d.open=states[i]);
});
function updateLab() {
  const su = Number(document.getElementById('su').value), sv = Number(document.getElementById('sv').value);
  const rho = Number(document.getElementById('rho').value);
  document.getElementById('rho-value').value=rho.toFixed(2);
  const status=document.getElementById('lab-status');
  if(!Number.isFinite(su)||!Number.isFinite(sv)||su<.001||sv<.001||su>10||sv>10){
    document.getElementById('sx').value='—';status.textContent='Enter errors between 0.001% and 10%.';status.classList.add('error');document.getElementById('ellipse-path').setAttribute('d','');return;
  }
  status.classList.remove('error');
  const product=document.getElementById('relationship').value==='product';
  const variance=su*su+sv*sv+(product?2:-2)*rho*su*sv;
  document.getElementById('sx').value=`${Math.sqrt(Math.max(0,variance)).toFixed(4)}%`;
  status.textContent=`Allowed relative error: ${Math.abs(su-sv).toFixed(4)}–${(su+sv).toFixed(4)}%. ${Math.abs(rho)===1?'At |ρ| = 1, the covariance is singular and the ellipse collapses to a line.':''}`;
  const scale=110/Math.max(su,sv);
  const points=[];
  for(let i=0;i<=160;i++){
    const t=2*Math.PI*i/160;
    const x=su*Math.cos(t),y=sv*(rho*Math.cos(t)+Math.sqrt(Math.max(0,1-rho*rho))*Math.sin(t));
    points.push(`${i?'L':'M'}${(190+x*scale).toFixed(3)},${(160-y*scale).toFixed(3)}`);
  }
  document.getElementById('ellipse-path').setAttribute('d',points.join(' ')+' Z');
  document.getElementById('ellipse-scale').textContent=`110 px = ${Math.max(su,sv).toPrecision(3)}%`;
  document.getElementById('ellipse-desc').textContent=`Input uncertainty contour with relative errors ${su}% and ${sv}%, and correlation ${rho.toFixed(2)}. Derived ${product?'product':'quotient'} error ${Math.sqrt(Math.max(0,variance)).toFixed(4)}%.`;
}
['su','sv','rho','relationship'].forEach(id=>document.getElementById(id).addEventListener('input',updateLab));
updateLab();
