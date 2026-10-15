"use strict";
(function(){
  var result=null, revision=0, chartPoints=[];
  var status=$("forecast-status"), holder=$("forecast-chart"), output=$("forecast-result");
  function number(v,digits){return v===null || v===undefined?"미산출":Number(v).toLocaleString("ko-KR",{maximumFractionDigits:digits===undefined?2:digits});}
  function pct(v){return v===null || v===undefined?"미산출":number(v,2)+"%";}
  function stat(parent,label,value,detail){var card=el("div",undefined,"forecast-stat");card.append(el("span",label),el("strong",value));if(detail)card.appendChild(el("small",detail));parent.appendChild(card);}
  window.invalidateForecast=function(reason){revision++;result=null;output.hidden=true;holder.replaceChildren();$("forecast-export").disabled=true;status.textContent=reason || "조건이 바뀌었습니다. 전망을 다시 계산하세요.";};
  function render(data){
    $("forecast-tooltip").textContent="차트 위를 움직이면 가격과 범위를 확인할 수 있습니다.";
    result=data;output.hidden=false;$("forecast-export").disabled=false;
    $("forecast-demo-notice").hidden=!data.demo;
    $("forecast-meta").textContent=data.symbol+" · "+data.currency+" · 종가 기준일 "+data.price_date+" · "+data.engine+" · 적합 "+data.lookback+"개 수익률";
    $("forecast-summary").replaceChildren();
    var end=data.future[data.future.length-1];
    stat($("forecast-summary"),"기준 종가",number(data.last_close)+" "+data.currency,data.price_date);
    stat($("forecast-summary"),"+"+data.horizon+"거래일 후 예상",number(end.estimate)+" "+data.currency,"기준 종가 대비 "+pct(data.projected_change));
    stat($("forecast-summary"),"마지막 관측의 참고 범위",end.lower===null?"자료 부족":number(end.lower)+" ~ "+number(end.upper),"목표 포함률 80% · 미래 포함 보장 없음");
    stat($("forecast-summary"),"오차 계산 구간",data.calibration.count+"개 출발점","일별 출발점은 서로 겹칩니다.");
    var v=data.validation, verdict;
    if(!v.count)verdict="가격 이력이 짧아 독립된 검증 구간 3개를 확보하지 못했습니다. 검증 지표를 산출하지 않습니다.";
    else if(v.relative_mae===null)verdict="비교 기준의 오차가 0이어서 상대 오차를 비교하지 못했습니다.";
    else verdict="과거 "+v.count+"개 구간에서 예측 오차는 기준종가 유지 방식보다 "+(v.relative_mae<1?"작았습니다.":v.relative_mae>1?"컸습니다.":"같았습니다.")+" 표본이 작으며 미래 성과를 뜻하지 않습니다.";
    $("forecast-verdict").textContent=verdict;$("forecast-verdict").className=v.relative_mae!==null && v.relative_mae>1?"forecast-caution":"muted";
    $("forecast-metrics").replaceChildren();
    stat($("forecast-metrics"),"예측의 평균 절대 비율 오차",pct(v.mape),"구간 마지막 가격 기준");
    stat($("forecast-metrics"),"기준종가 유지의 같은 오차",pct(v.baseline_mape),"모델의 비교 기준");
    stat($("forecast-metrics"),"방향 일치율",pct(v.direction_accuracy),"겹치지 않는 "+v.count+"개 구간");
    stat($("forecast-metrics"),"실제 가격의 범위 포함률",pct(v.interval_coverage),"검증 시작 전 고정한 오차 범위");
    var table=$("forecast-validation-table");table.replaceChildren();var head=el("tr");
    ["출발일","검증 종료일","예측","실제","종가 유지","범위 포함"].forEach(function(label){head.appendChild(el("th",label));});table.appendChild(head);
    v.rows.forEach(function(row){var tr=el("tr");[row.origin,row.target,number(row.estimate),number(row.actual),number(row.baseline),row.covered?"포함":"벗어남"].forEach(function(value){tr.appendChild(el("td",value));});table.appendChild(tr);});
    $("forecast-source").replaceChildren();$("forecast-source").appendChild(el("p",data.source.title));
    if(data.source.url && data.source.url.startsWith("https://")){var link=el("a","공개 데이터 출처 ↗");link.href=data.source.url;link.target="_blank";link.rel="noopener";$("forecast-source").appendChild(link);}
    $("forecast-source").appendChild(el("p","기준 버전 "+data.version+" · 요청 기준일 "+data.as_of+" · 마지막 가격 "+data.price_date));
    $("forecast-warnings").replaceChildren();data.warnings.forEach(function(w){$("forecast-warnings").appendChild(el("li",w));});
    status.textContent=(data.demo?"가상 차트입니다. ":"")+data.symbol+" 가격을 기준으로 "+data.horizon+"거래일의 전망을 계산했습니다.";
    draw();
  }
  function svgNode(tag,attrs,text){var n=document.createElementNS("http://www.w3.org/2000/svg",tag);Object.entries(attrs || {}).forEach(function(v){n.setAttribute(v[0],v[1]);});if(text!==undefined)n.textContent=text;return n;}
  function draw(){
    if(!result || $("view-forecast").hidden || holder.clientWidth<100)return;
    var data=result, width=Math.max(280,holder.clientWidth),height=360,left=width<500?58:76,right=18,top=30,bottom=35;
    var history=data.history.slice(-Number($("forecast-display").value)),n=history.length,total=n+data.future.length;
    var all=history.map(function(p){return p.close;});data.future.forEach(function(p){all.push(p.estimate);if(p.lower!==null)all.push(p.lower,p.upper);});
    var low=Math.min.apply(null,all),high=Math.max.apply(null,all),pad=(high-low)*.08 || Math.max(high*.05,1);low=Math.max(0,low-pad);high+=pad;
    function x(i){return left+i/(total-1)*(width-left-right);}
    function y(v){return top+(high-v)/(high-low)*(height-top-bottom);}
    var svg=svgNode("svg",{viewBox:"0 0 "+width+" "+height,width:"100%",height:height,role:"img","aria-label":data.symbol+" 과거 종가와 향후 "+data.horizon+"거래일의 예상 경로 및 오차 범위"});
    svg.appendChild(svgNode("title",{},"가격 전망 · 기준 종가 "+data.price_date+" · 미래 X축은 거래일 순서"));
    for(var j=0;j<=4;j++){var v=low+(high-low)*j/4,yy=y(v);svg.appendChild(svgNode("line",{x1:left,x2:width-right,y1:yy,y2:yy,class:"forecast-grid"}));svg.appendChild(svgNode("text",{x:left-8,y:yy+4,"text-anchor":"end",class:"forecast-axis"},number(v,high<10?3:0)));}
    function line(points,cls){svg.appendChild(svgNode("polyline",{points:points.map(function(p){return x(p.i)+","+y(p.v);}).join(" "),fill:"none",class:cls}));}
    var anchor={i:n-1,v:data.last_close},path=[anchor].concat(data.future.map(function(p,i){return{i:n+i,v:p.estimate};}));
    if(data.future[0].lower!==null){var band=[anchor].concat(data.future.map(function(p,i){return{i:n+i,v:p.upper};})).concat(data.future.map(function(p,i){return{i:n+i,v:p.lower};}).reverse()).concat([anchor]);svg.appendChild(svgNode("polygon",{points:band.map(function(p){return x(p.i)+","+y(p.v);}).join(" "),class:"forecast-area"}));}
    line(history.map(function(p,i){return{i:i,v:p.close};}),"forecast-history");
    line([anchor,{i:total-1,v:data.last_close}],"forecast-baseline");line(path,"forecast-estimate");
    svg.appendChild(svgNode("line",{x1:x(n-1),x2:x(n-1),y1:top,y2:height-bottom,class:"forecast-boundary"}));
    svg.appendChild(svgNode("text",{x:x(n-1)-5,y:17,"text-anchor":"end",class:"forecast-axis"},"전망 시작"));
    [0,Math.floor(n/2)].forEach(function(i){svg.appendChild(svgNode("text",{x:x(i),y:height-10,"text-anchor":i===0?"start":"middle",class:"forecast-axis"},history[i].date));});
    svg.appendChild(svgNode("text",{x:width-right,y:height-10,"text-anchor":"end",class:"forecast-axis"},"+"+data.horizon+"거래일"));
    chartPoints=history.map(function(p){return{label:p.date,value:p.close};}).concat(data.future.map(function(p){return{label:"+"+p.step+"거래일",value:p.estimate,lower:p.lower,upper:p.upper};}));
    var cross=svgNode("line",{y1:top,y2:height-bottom,class:"forecast-cross",visibility:"hidden"}),dot=svgNode("circle",{r:4,class:"forecast-dot",visibility:"hidden"});svg.append(cross,dot);
    svg.addEventListener("pointermove",function(event){var rect=svg.getBoundingClientRect(),xx=(event.clientX-rect.left)/rect.width*width,index=Math.max(0,Math.min(total-1,Math.round((xx-left)/(width-left-right)*(total-1)))),p=chartPoints[index];cross.setAttribute("x1",x(index));cross.setAttribute("x2",x(index));cross.setAttribute("visibility","visible");dot.setAttribute("cx",x(index));dot.setAttribute("cy",y(p.value));dot.setAttribute("visibility","visible");$("forecast-tooltip").textContent=p.label+" · "+number(p.value)+" "+data.currency+(p.lower!==undefined && p.lower!==null?" · 참고 범위 "+number(p.lower)+" ~ "+number(p.upper):"");});
    svg.addEventListener("pointerleave",function(){cross.setAttribute("visibility","hidden");dot.setAttribute("visibility","hidden");});
    holder.replaceChildren(svg);
  }
  window.resizeForecast=function(){requestAnimationFrame(draw);};
  async function run(demo){
    var local=++revision;
    result=null;output.hidden=true;$("forecast-export").disabled=true;$("forecast-run").disabled=true;$("forecast-demo").disabled=true;
    status.textContent="가격을 확인하고 과거 구간 오차를 계산하고 있습니다…";
    try{
      var input={symbol:$("symbol").value.trim(),market:$("market").value,as_of:$("as-of").value || today(),offline:$("offline").checked,horizon:Number($("forecast-horizon").value),lookback:Number($("forecast-lookback").value),method:$("forecast-method").value,demo:demo || Boolean(state && state.demo && $("symbol").value.trim()==="DEMO")};
      var response=await api("/api/forecast",input);
      if(local!==revision)return;
      render(response);
    }catch(e){if(local===revision)status.textContent=e.message;}
    finally{$("forecast-run").disabled=false;$("forecast-demo").disabled=false;}
  }
  $("forecast-run").onclick=function(){run(false);};$("forecast-demo").onclick=function(){run(true);};
  $("forecast-export").onclick=function(){if(result)download(result.symbol+"-chart-forecast.json",JSON.stringify(result,null,2),"application/json");};
  ["symbol","market","as-of","offline","forecast-horizon","forecast-lookback","forecast-method"].forEach(function(id){$(id).addEventListener("input",function(){window.invalidateForecast();});});
  $("forecast-display").oninput=function(){$("forecast-tooltip").textContent="차트 위를 움직이면 가격과 범위를 확인할 수 있습니다.";draw();};
  if(window.ResizeObserver)new ResizeObserver(function(){if(result)draw();}).observe(holder);
})();
