"use strict";
var API_BASE = location.pathname.startsWith("/gems/") ? "/gems" : "";
var catalog, state = null, calculated = null, stale = true, inputRevision = 0;
var $ = function(id) { return document.getElementById(id); };
function el(tag, text, cls) { var n = document.createElement(tag); if (text !== undefined) n.textContent = text; if (cls) n.className = cls; return n; }
function today() { return new Intl.DateTimeFormat("sv-SE",{timeZone:"Asia/Seoul"}).format(new Date()); }
function message(text) { $("message").textContent = text; $("message").hidden = !text; }
async function api(url, data) {
  var response = await fetch(API_BASE + url, data === undefined ? {} : {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
  var body = await response.json();
  if (!response.ok) { throw new Error(typeof body.detail === "string" ? body.detail : "입력값을 확인하세요: " + JSON.stringify(body.detail)); }
  return body;
}
function showView(name) {
  window.scrollTo(0,0);
  document.querySelectorAll(".view").forEach(function(n){ n.hidden = n.id !== "view-" + name; });
  document.querySelectorAll("[data-view]").forEach(function(n){ n.classList.toggle("active",n.dataset.view === name); });
  if(embedded) window.parent.postMessage({type:"gems-view-changed",view:name},location.origin);
  if (name === "history") loadHistory();
  if (name === "review" && state) runReview().catch(function(e){message(e.message);});
  if (name === "forecast" && window.resizeForecast) window.resizeForecast();
}
function markStale() {
  inputRevision++;
  stale = true; $("save").disabled = true;
  if (calculated) { $("total").textContent="—"; $("provisional").textContent="—"; $("readiness").textContent = "입력 변경"; $("score-caption").textContent = "입력이 바뀌었습니다. 다시 계산하세요."; }
}
function field(parent, label, tag, className) {
  var wrap = el("label",label,className), input = el(tag || "input");
  wrap.appendChild(input); parent.appendChild(wrap); return input;
}
function buildCriteria() {
  catalog.groups.forEach(function(group,index){
    var link = el("a",group.label,"group-link"); link.href = "#group-" + group.id;
    link.onclick = function(){ showView("evaluate"); }; $("group-nav").appendChild(link);
    var section = el("section",undefined,"group panel"); section.id = "group-" + group.id;
    var header = el("div",undefined,"section-title"); header.appendChild(el("span",String(index+1).padStart(2,"0"),"number"));
    header.appendChild(el("h2",group.label)); header.appendChild(el("span",group.weight + "%","weight")); section.appendChild(header);
    catalog.criteria.filter(function(c){ return c.group === group.id; }).forEach(function(c){
      var card = el("div",undefined,"criterion"); card.dataset.criterion = c.id;
      var row = el("div",undefined,"criterion-main"), left = el("div");
      left.appendChild(el("div",c.label,"criterion-name")); left.appendChild(el("div",c.guide,"criterion-guide"));
      var valueWrap = el("div",undefined,"criterion-value"), input;
      if (c.kind === "qualitative" || c.kind === "choice") {
        if(c.kind === "qualitative") valueWrap.appendChild(el("div","근거에 따른 검토자 평가","qual-label"));
        input = el("select"); input.appendChild(new Option("미평가",""));
        if(c.kind === "qualitative") { for(var i=1;i<=5;i++) input.appendChild(new Option(i+"점",i)); }
        else Object.entries(c.options).forEach(function(p){ input.appendChild(new Option(p[1],p[0])); });
      } else { input = el("input"); input.type = "number"; input.step = "any"; valueWrap.appendChild(el("span",c.unit || "","unit")); }
      input.className = "metric-value"; input.setAttribute("aria-label",c.label); valueWrap.appendChild(input);
      row.append(left,valueWrap); card.appendChild(row);
      var toggle = el("button","+ 근거와 출처 입력","evidence-toggle"), status = el("span","","item-status");
      var fields = el("div",undefined,"evidence-fields"); fields.hidden = true;
      toggle.type = "button"; toggle.onclick = function(){ fields.hidden = !fields.hidden; toggle.textContent = fields.hidden ? "+ 근거와 출처 입력" : "− 근거와 출처 접기"; };
      card.append(toggle,status,fields);
      var evidence = field(fields,"판단 근거·계산 기간","textarea","wide"); evidence.rows=2; evidence.className="evidence";
      var title = field(fields,"출처명"); title.className="source-title"; title.placeholder="공시·IR·검토 자료";
      var sourceDate = field(fields,"자료 기준일"); sourceDate.type="date"; sourceDate.className="source-date";
      var url = field(fields,"출처 URL · 선택"); url.className="source-url"; url.type="url"; url.placeholder="https://";
      var kind = field(fields,"자료 성격","select"); kind.className="source-kind";
      [["fact","확인된 사실"],["estimate","추정치"],["assumption","검토자 가정"]].forEach(function(v){ kind.appendChild(new Option(v[1],v[0])); });
      if(c.id === "dividend"){
        var regular = field(fields,"정기 배당","select"); regular.className="regular";
        [["","미확인"],["true","예"],["false","아니요"]].forEach(function(v){ regular.appendChild(new Option(v[1],v[0])); });
        var years = field(fields,"배당 연속 증가 연수"); years.type="number"; years.min="0"; years.className="growth-years";
        var cut = field(fields,"최근 배당 삭감","select"); cut.className="cut";
        [["false","아니요"],["true","예"]].forEach(function(v){ cut.appendChild(new Option(v[1],v[0])); });
      }
      if(c.id === "profit_cagr"){
        var loss = field(fields,"최근 연간 순이익 적자","select"); loss.className="loss";
        [["false","아니요 또는 미확인"],["true","확인된 적자"]].forEach(function(v){ loss.appendChild(new Option(v[1],v[0])); });
      }
      if(c.id === "debt_ratio"){
        var equity = field(fields,"자본총계 0 이하","select"); equity.className="nonpositive-equity";
        [["false","아니요 또는 미확인"],["true","확인됨"]].forEach(function(v){ equity.appendChild(new Option(v[1],v[0])); });
        var coverage = field(fields,"이자보상배율 · 선택"); coverage.type="number"; coverage.step="any"; coverage.className="interest-coverage";
      }
      section.appendChild(card);
    });
    $("criteria").appendChild(section);
  });
  for(var i=0;i<3;i++){
    var row = el("div",undefined,"peer-row");
    ["경쟁사 이름","성장률·수익성·밸류에이션","출처·기준일"].forEach(function(text){var n=el("input");n.placeholder=text;row.appendChild(n);});
    $("peers").appendChild(row);
  }
}
function renderInput(data) {
  if(window.invalidateForecast && state && (data.symbol!==state.symbol || data.market!==state.market || data.as_of!==state.as_of || data.demo!==state.demo)) window.invalidateForecast("분석 대상이나 기준일이 바뀌었습니다. 전망을 다시 계산하세요.");
  inputRevision++;
  state = data; calculated = null; stale = true;
  $("symbol").value=data.symbol; $("market").value=data.market; $("profile").value=data.profile || "general"; $("as-of").value=data.as_of;
  $("demo-banner").hidden=!data.demo;
  $("instrument-meta").textContent=(data.name || data.symbol) + " · " + (data.notes || []).join(" ") + (data.demo ? " · 가상 데이터" : "");
  document.querySelectorAll("[data-criterion]").forEach(function(card){
    var c=catalog.criteria.find(function(v){return v.id===card.dataset.criterion;}), o=data.observations[c.id] || {}, s=(o.sources || [])[0] || {}, ctx=o.context || {};
    card.querySelector(".metric-value").value=(c.kind==="qualitative" ? o.score : o.value) ?? "";
    card.querySelector(".evidence").value=o.evidence || "";
    card.querySelector(".source-title").value=s.title || ""; card.querySelector(".source-date").value=s.as_of || "";
    card.querySelector(".source-url").value=s.url || ""; card.querySelector(".source-kind").value=s.kind || "fact";
    card.querySelector(".item-status").textContent=""; card.querySelector(".evidence-fields").hidden=true;
    card.querySelector(".evidence-toggle").textContent="+ 근거와 출처 입력";
    if(c.id==="dividend"){card.querySelector(".regular").value=ctx.regular===undefined?"":String(ctx.regular);card.querySelector(".growth-years").value=ctx.growth_years ?? "";card.querySelector(".cut").value=String(ctx.cut_recently===true);}
    if(c.id==="profit_cagr") card.querySelector(".loss").value=String(ctx.loss===true);
    if(c.id==="debt_ratio"){card.querySelector(".nonpositive-equity").value=String(ctx.nonpositive_equity===true);card.querySelector(".interest-coverage").value=ctx.interest_coverage ?? "";}
  });
  $("thesis").value=(data.thesis || []).join("\n"); $("risks").value=(data.risks || []).join("\n");
  $("current-price").value=data.current_price ?? ""; $("target-price").value=data.target_price ?? "";
  $("price-date").value=data.price_date || ""; $("target-basis").value=data.target_basis || "";
  document.querySelectorAll(".peer-row").forEach(function(row,i){var p=(data.peers || [])[i] || {};row.querySelectorAll("input").forEach(function(n,j){n.value=[p.name,p.metrics,p.source][j] || "";});});
  $("total").textContent="—";$("coverage").textContent="0%";$("coverage-bar").style.width="0";$("range").textContent="0 ~ 100";$("provisional").textContent="—";$("readiness").textContent="미평가";
  $("score-caption").textContent="입력 근거를 확인한 뒤 매력도를 계산하세요."; $("save").disabled=true; $("group-scores").replaceChildren();
  $("basis").textContent="자료 성격: 미입력";
  $("review-checks").textContent="현재 입력으로 재무 검토를 실행하세요."; $("review-workflows").replaceChildren();
  $("report-content").textContent="현재 입력으로 다시 계산하면 보고서를 확인할 수 있습니다.";
}
function readInput(){
  var symbol=$("symbol").value.trim(), market=$("market").value;
  if((symbol!==state.symbol || market!==state.market) && Object.keys(state.observations).length) throw new Error("분석 대상이 바뀌었습니다. 새 종목의 DartLab 데이터를 불러오거나 빈 입력에서 시작하세요.");
  var data=structuredClone(state); data.symbol=symbol;data.market=market;data.profile=$("profile").value;data.as_of=$("as-of").value;data.observations={};
  if(data.name==="새 분석")data.name=symbol;
  document.querySelectorAll("[data-criterion]").forEach(function(card){
    var id=card.dataset.criterion,c=catalog.criteria.find(function(v){return v.id===id;}),v=card.querySelector(".metric-value").value;
    var original=state.observations[id] || {},ctx=structuredClone(original.context || {}),evidence=card.querySelector(".evidence").value.trim();
    if(id==="dividend"){var regular=card.querySelector(".regular").value;if(regular)ctx.regular=regular==="true";else delete ctx.regular;var years=card.querySelector(".growth-years").value;if(years!=="")ctx.growth_years=Number(years);else delete ctx.growth_years;ctx.cut_recently=card.querySelector(".cut").value==="true";}
    if(id==="profit_cagr")ctx.loss=card.querySelector(".loss").value==="true";
    if(id==="debt_ratio"){ctx.nonpositive_equity=card.querySelector(".nonpositive-equity").value==="true";var ic=card.querySelector(".interest-coverage").value;if(ic!=="")ctx.interest_coverage=Number(ic);else delete ctx.interest_coverage;}
    if(v==="" && !evidence && !ctx.loss) return;
    var observation={value:null,score:null,evidence:evidence,sources:[],context:ctx};
    if(c.kind==="qualitative")observation.score=v===""?null:Number(v);else observation.value=v===""?null:c.kind==="number"?Number(v):v;
    var title=card.querySelector(".source-title").value.trim(),d=card.querySelector(".source-date").value;
    if(title && d)observation.sources=[{title:title,as_of:d,url:card.querySelector(".source-url").value.trim(),kind:card.querySelector(".source-kind").value}].concat((original.sources || []).slice(1));
    data.observations[id]=observation;
  });
  ["thesis","risks"].forEach(function(k){data[k]=$(k).value.split("\n").filter(function(v){return v.trim();}).slice(0,3);});
  data.current_price=$("current-price").value===""?null:Number($("current-price").value);
  data.target_price=$("target-price").value===""?null:Number($("target-price").value);
  data.price_date=$("price-date").value || null;data.target_basis=$("target-basis").value;
  data.peers=[];document.querySelectorAll(".peer-row").forEach(function(row){var v=Array.from(row.querySelectorAll("input")).map(function(n){return n.value.trim();});if(v[0])data.peers.push({name:v[0],metrics:v[1],source:v[2]});});
  return data;
}
function renderResult(response){
  var r=response.result;calculated=response;stale=false;
  $("total").textContent=r.score===null?"—":r.score.toFixed(1);$("readiness").textContent=r.status==="complete"?"평가 완료":"잠정 평가";
  $("score-caption").textContent=r.band+" · "+r.scored_count+"/"+r.total_count+"개 항목";
  $("coverage").textContent=r.coverage.toFixed(1)+"%";$("coverage-bar").style.width=r.coverage+"%";
  $("range").textContent=r.score_range[0].toFixed(1)+" ~ "+r.score_range[1].toFixed(1);
  $("provisional").textContent=r.provisional_score===null?"—":r.provisional_score.toFixed(1);$("save").disabled=false;
  var b=r.evidence_basis;$("basis").textContent="자료 성격별 가중치 · 사실 "+b.fact+"% / 추정 "+b.estimate+"% / 가정 "+b.assumption+"%";
  $("group-scores").replaceChildren();
  r.groups.forEach(function(g){
    var row=el("div",undefined,"mini-group");row.append(el("span",g.label),el("span",g.average===null?"미평가":g.average+" / 5"));
    var track=el("i"),fill=el("b");fill.style.width=(g.average===null?0:(g.average-1)/4*100)+"%";track.appendChild(fill);row.appendChild(track);$("group-scores").appendChild(row);
    g.items.forEach(function(item){var n=document.querySelector('[data-criterion="'+item.id+'"] .item-status');n.textContent=item.score===null?item.reason:item.score+"점";n.className="item-status"+(item.score!==null?" scored":"");});
  });
  $("report-content").textContent=response.report;
  if(response.review) renderReview(response.review);
}
async function calculate(){
  try{message("");var revision=inputRevision,data=readInput(),response=await api("/api/analyze",data);if(revision!==inputRevision)throw new Error("계산 중 입력이 바뀌었습니다. 다시 계산하세요.");state=response.input;renderResult(response);return response.input;}catch(e){message(e.message);throw e;}
}
function download(name,text,type){var u=URL.createObjectURL(new Blob([text],{type:type})),a=el("a");a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(function(){URL.revokeObjectURL(u);},1000);}
async function loadHistory(){
  try{
    var rows=await api("/api/history");$("history-list").replaceChildren();
    if(!rows.length){$("history-list").appendChild(el("p","저장된 분석이 없습니다.","muted"));return;}
    rows.forEach(function(row){var n=el("div",undefined,"history-row"),text=el("div"),savedAt=new Date(row.created_at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul",hour12:false})+" KST";text.append(el("strong",(row.demo?"[가상 예시] ":"")+(row.name || row.symbol)),el("small",savedAt+" · "+row.rubric_version+" · 자료 "+row.coverage+"%"));var button=el("button","열기","button secondary");button.onclick=async function(){try{var item=await api("/api/history/"+row.id);renderInput(item.payload);showView("evaluate");await calculate();}catch(e){message(e.message);}};n.append(text,button);$("history-list").appendChild(n);});
  }catch(e){message(e.message);}
}
async function init(){
  try{
    catalog=await api("/api/rubric");$("version").textContent=catalog.version;buildCriteria();
    renderInput({symbol:"005930",market:"KR",name:"새 분석",profile:"general",as_of:today(),observations:{},notes:[],demo:false});
    document.querySelectorAll("[data-view]").forEach(function(n){n.onclick=function(){showView(n.dataset.view);};});
    document.querySelectorAll("input,textarea,select").forEach(function(n){if(!n.closest("#view-forecast"))n.addEventListener("input",markStale);});
    $("demo").onclick=async function(){try{message("");renderInput(await api("/api/demo"));showView("evaluate");await calculate();}catch(e){message(e.message);}};
    $("reset").onclick=function(){message("");renderInput({symbol:$("symbol").value.trim() || "005930",market:$("market").value,name:"새 분석",profile:$("profile").value,as_of:today(),observations:{},notes:[],demo:false});showView("evaluate");};
    $("load").onclick=async function(){var revision=inputRevision,b=$("load");b.disabled=true;b.textContent="공개 데이터 확인 중…";message("첫 조회는 파일 다운로드에 시간이 걸릴 수 있습니다.");try{var data=await api("/api/company",{symbol:$("symbol").value.trim(),market:$("market").value,offline:$("offline").checked});if(revision!==inputRevision){message("조회 중 입력이 바뀌어 받은 자료를 적용하지 않았습니다. 현재 입력을 보존했습니다.");return;}renderInput(data);message("");await calculate();}catch(e){message(e.message);}finally{b.disabled=false;b.textContent="DartLab 불러오기";}};
    $("review-run").onclick=function(){runReview().catch(function(e){message(e.message);});};
    $("copy-review").onclick=async function(){try{var review=await runReview();await navigator.clipboard.writeText(review.prompt);message("검토 요청을 복사했습니다. DartLab AI 채팅이나 Gems에 붙여 넣으세요.");}catch(e){message(e.message);}};
    $("calculate").onclick=function(){calculate().catch(function(){});};
    $("save").onclick=async function(){try{var data=await calculate();var result=await api("/api/save",data);message("입력 근거와 "+result.result.rubric_version+" 기준을 함께 로컬에 저장했습니다.");}catch(e){message(e.message);}};
    $("export-md").onclick=async function(){try{var data=await calculate();download(data.symbol+"-research.md",calculated.report,"text/markdown;charset=utf-8");}catch(e){message(e.message);}};
    $("export-json").onclick=async function(){try{var data=await calculate();download(data.symbol+"-evidence.json",JSON.stringify(data,null,2),"application/json");}catch(e){message(e.message);}};
    $("copy-gems").onclick=async function(){try{await calculate();await navigator.clipboard.writeText(calculated.gems_prompt);message("Gems 검토 요청을 복사했습니다. 기준서와 함께 사용하세요.");}catch(e){message(e.message);}};
    $("import-json").onchange=async function(event){var file=event.target.files[0];if(!file)return;try{var data=JSON.parse(await file.text());if(data.version && String(data.version).startsWith("price-forecast-"))throw new Error("차트 전망 JSON은 매력도 평가의 근거 JSON과 다른 파일입니다.");var response=await api("/api/analyze",data);renderInput(response.input);showView("evaluate");await calculate();message("입력 파일을 불러왔습니다.");}catch(e){message("파일을 확인하세요: "+e.message);}event.target.value="";};
  }catch(e){message("화면 초기화 실패: "+e.message);}
}
function renderReview(review){
  $("review-checks").replaceChildren(); $("review-workflows").replaceChildren();
  review.checks.forEach(function(check){var row=el("div",undefined,"review-check");row.append(el("strong",check.label),el("span",check.status==="ready"?"입력 확인":check.status==="warning"?"검토 필요":"자료 보완","pill"),el("p",check.detail));$("review-checks").appendChild(row);});
  review.workflows.forEach(function(flow){var box=el("section",undefined,"review-flow");box.append(el("h3",flow.title),el("p",flow.description));var list=el("ul");flow.questions.forEach(function(q){list.appendChild(el("li",q));});box.appendChild(list);var link=el("a","financial-services 원문 ↗");link.href=API_BASE+"/api/workflows/"+flow.id;link.target="_blank";link.rel="noopener";box.appendChild(link);$("review-workflows").appendChild(box);});
}
async function runReview(){var revision=inputRevision,review=await api("/api/review",readInput());if(revision!==inputRevision)throw new Error("검토 중 입력이 바뀌었습니다. 다시 점검하세요.");renderReview(review);return review;}
var embedded = new URLSearchParams(location.search).get("embedded")==="1";
if(embedded) document.documentElement.classList.add("embedded");
window.addEventListener("message",async function(event){
  if(!embedded || event.source!==window.parent || event.origin!==location.origin || !state) return;
  var payload=event.data || {};
  if(payload.type==="gems-context"){
    var code=String(payload.symbol || "");
    if(!/^[A-Za-z0-9.^_-]{1,20}$/.test(code)) return;
    if(code!==state.symbol){message("DartLab 조회 종목: "+code+". 현재 입력을 보존했습니다. 새 분석을 시작하거나 DartLab 데이터를 불러오세요.");return;}
  }
  if(payload.type==="gems-select-company"){
    var next=String(payload.symbol || "");
    if(!/^[A-Za-z0-9.^_-]{1,20}$/.test(next)) return;
    var hasInputs;try{hasInputs=Object.keys(readInput().observations).length;}catch(_){hasInputs=Object.keys(state.observations).length;}
    if(hasInputs && !confirm("현재 입력을 새 종목으로 바꿉니다. 저장하지 않은 변경은 사라집니다. 계속할까요?")) return;
    renderInput({symbol:next,market:/^\d{6}$/.test(next)?"KR":"US",name:"새 분석",profile:"general",as_of:today(),observations:{},notes:[],demo:false});
    $("load").click();
  }
  if(payload.type==="gems-view" && ["evaluate","review","report","history","forecast"].includes(payload.view)) showView(payload.view);
});
init().then(function(){
  if(!state) return;
  var query=new URLSearchParams(location.search),code=query.get("symbol");
  if(code && /^[A-Za-z0-9.^_-]{1,20}$/.test(code)) renderInput({symbol:code,market:/^\d{6}$/.test(code)?"KR":"US",name:"새 분석",profile:"general",as_of:today(),observations:{},notes:[],demo:false});
  if(embedded) { window.parent.postMessage({type:"gems-ready"},location.origin); if(code && query.get("view")!=="forecast") $("load").click(); }
});
