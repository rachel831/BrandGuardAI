import { useEffect, useRef, useState } from "react";
import {
  ShieldCheck, LayoutDashboard, FileSearch, BookOpen, History, Plus, Trash2,
  UploadCloud, ScanSearch, CheckCircle2, AlertTriangle, ThumbsUp, RotateCcw,
  Ban, RefreshCw, Power, FileText, LogOut, UserPlus, LockKeyhole
} from "lucide-react";

const API = "http://127.0.0.1:8000";
const TOKEN_KEY = "brandguard_token";
const blankGuideline = { brand_name:"", tone_of_voice:"", approved_colors:[], restricted_terms:[], approved_claims:[], approved_terms:[], required_terms:[], brand_facts:[], logo_url:"", logo_filename:"" };
const arr = v => Array.isArray(v) ? v : [];
const lines = v => v.split(/\r?\n/).filter(x=>x.trim().length>0);
const dateText = v => v ? new Date(v).toLocaleString() : "—";

export default function App() {
  const [user,setUser] = useState(null);
  const [token,setToken] = useState(localStorage.getItem(TOKEN_KEY) || "");
  const [authMode,setAuthMode] = useState("login");
  const [authName,setAuthName] = useState("");
  const [authEmail,setAuthEmail] = useState("");
  const [authPassword,setAuthPassword] = useState("");
  const [authBusy,setAuthBusy] = useState(false);
  const [page,setPage] = useState("Dashboard");
  const [text,setText] = useState("");
  const [textReport,setTextReport] = useState(null);
  const [textReviewId,setTextReviewId] = useState(null);
  const [textDecision,setTextDecision] = useState("Pending Review");
  const [textNote,setTextNote] = useState("");
  const [image,setImage] = useState(null);
  const [imageReport,setImageReport] = useState(null);
  const [imageReviewId,setImageReviewId] = useState(null);
  const [imageDecision,setImageDecision] = useState("Pending Review");
  const [imageNote,setImageNote] = useState("");
  const [busy,setBusy] = useState(false);
  const [imageBusy,setImageBusy] = useState(false);
  const [history,setHistory] = useState([]);
  const [historyBusy,setHistoryBusy] = useState(false);
  const [selectedReviewId,setSelectedReviewId] = useState(null);
  const [historyReviewerNote,setHistoryReviewerNote] = useState("");
  const [guideline,setGuideline] = useState(blankGuideline);
  const [guidelineHistory,setGuidelineHistory] = useState([]);
  const [guidelineBusy,setGuidelineBusy] = useState(false);
  const [guidelineSaving,setGuidelineSaving] = useState(false);
  const [pendingLogo,setPendingLogo] = useState(null);
  const [analytics,setAnalytics] = useState(null);
  const [analyticsBusy,setAnalyticsBusy] = useState(false);
  const [isNewGuideline,setIsNewGuideline] = useState(false);
  const [message,setMessage] = useState("");
  const [error,setError] = useState("");
  const fileRef = useRef(null);

  async function request(path, options={}) {
    const headers = new Headers(options.headers || {});
    const activeToken = localStorage.getItem(TOKEN_KEY);
    if (activeToken) headers.set("Authorization", `Bearer ${activeToken}`);
    const response = await fetch(`${API}${path}`, {...options, headers});
    const data = await response.json().catch(()=>({}));
    if (response.status === 401 && path !== "/auth/login" && path !== "/auth/register") {
      logout(false);
      throw new Error("Your session expired. Please log in again.");
    }
    if (!response.ok) throw new Error(data.detail || data.message || "The request failed.");
    return data;
  }

  async function acceptSession(data) {
    localStorage.setItem(TOKEN_KEY,data.token);
    setToken(data.token); setUser(data.user); setPage("Dashboard");
    setError(""); setMessage(`Welcome, ${data.user.name}.`);
    setText(""); setTextReport(null); setImage(null); setImageReport(null);
    await loadHistory();
    if (data.user.role === "manager") {
      await loadGuidelines();
      await loadGuidelineHistory();
    }
  }

  async function submitAuth(event) {
    event.preventDefault(); setAuthBusy(true); setError(""); setMessage("");
    try {
      if (authMode === "register") {
        const data = await request("/auth/register", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({name:authName,email:authEmail,password:authPassword})
        });
        await acceptSession(data);
      } else {
        const data = await request("/auth/login", {
          method:"POST", headers:{"Content-Type":"application/json"},
          body:JSON.stringify({email:authEmail,password:authPassword})
        });
        await acceptSession(data);
      }
    } catch(e) { setError(e.message); }
    finally { setAuthBusy(false); }
  }

  async function demoLogin(role) {
    const credentials = role === "manager"
      ? {email:"manager@brandguard.demo",password:"ManagerDemo123!"}
      : {email:"creator@brandguard.demo",password:"CreatorDemo123!"};
    setAuthBusy(true); setError("");
    try {
      const data = await request("/auth/login", {
        method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(credentials)
      });
      await acceptSession(data);
    } catch(e) { setError(e.message); }
    finally { setAuthBusy(false); }
  }

  function logout(showMessage=true) {
    localStorage.removeItem(TOKEN_KEY); setToken(""); setUser(null);
    setHistory([]); setGuidelineHistory([]); setGuideline(blankGuideline);
    setText(""); setTextReport(null); setImage(null); setImageReport(null);
    setPage("Dashboard"); setError(""); setMessage(showMessage ? "You have logged out." : "");
  }

  useEffect(() => {
    let cancelled = false;
    async function restoreSession() {
      if (!token) return;
      try {
        const data = await request("/auth/me");
        if (cancelled) return;
        setUser(data.user);
        await loadHistory();
        if (data.user.role === "manager") {
          await loadGuidelines();
          await loadGuidelineHistory();
        }
      } catch(e) { if (!cancelled) setError(e.message); }
    }
    restoreSession();
    return () => { cancelled = true; };
  }, []);

  async function loadHistory() {
    setHistoryBusy(true);
    try { const data=await request("/reviews"); setHistory(arr(data.reviews)); await loadAnalytics(); }
    catch(e) { setError(e.message); }
    finally { setHistoryBusy(false); }
  }
  async function loadGuidelines() {
    setGuidelineBusy(true);
    try {
      const d=await request("/brand-guidelines");
      setGuideline({brand_name:d.brand_name||"",tone_of_voice:d.tone_of_voice||"",
        approved_colors:arr(d.approved_colors),restricted_terms:arr(d.restricted_terms),approved_claims:arr(d.approved_claims),
        approved_terms:arr(d.approved_terms),required_terms:arr(d.required_terms),brand_facts:arr(d.brand_facts),
        logo_url:d.logo_url||"",logo_filename:d.logo_filename||""});
      setIsNewGuideline(false);
    } catch(e) { setError(e.message); }
    finally { setGuidelineBusy(false); }
  }
  async function loadAnalytics() {
    setAnalyticsBusy(true);
    try { const d=await request("/analytics"); setAnalytics(d); }
    catch(e) { setError(e.message); }
    finally { setAnalyticsBusy(false); }
  }
  async function loadGuidelineHistory() {
    try { const d=await request("/brand-guidelines/history"); setGuidelineHistory(arr(d.guidelines)); }
    catch(e) { setError(e.message); }
  }
  function newAnalysis() {
    setText("");setTextReport(null);setTextReviewId(null);setTextDecision("Pending Review");setTextNote("");
    setImage(null);setImageReport(null);setImageReviewId(null);setImageDecision("Pending Review");setImageNote("");
    if(fileRef.current)fileRef.current.value="";
    setMessage("Workspace cleared. Saved reports remain in Review History.");setError("");
  }
  async function analyzeText() {
    if(!text.trim())return setError("Please paste some content before analysing.");
    setBusy(true);setError("");setMessage("");setTextReport(null);setTextReviewId(null);
    setImage(null);setImageReport(null);setImageReviewId(null);if(fileRef.current)fileRef.current.value="";
    try {
      const d=await request("/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({content:text})});
      setTextReport({...d,score:Math.max(0,100-Number(d.total_issues||0)*20)});
      setTextReviewId(d.review_id);setTextDecision("Pending Review");await loadHistory();
    } catch(e){setError(e.message);} finally{setBusy(false);}
  }
  function chooseImage(event) {
    const f=event.target.files?.[0];if(!f)return;
    if(!["image/jpeg","image/png","image/webp"].includes(f.type)){setError("Choose a JPG, PNG or WebP image.");event.target.value="";return;}
    if(f.size>5*1024*1024){setError("The image must be smaller than 5 MB.");event.target.value="";return;}
    setText("");setTextReport(null);setTextReviewId(null);setImage(f);setImageReport(null);setImageReviewId(null);
    setImageDecision("Pending Review");setImageNote("");setError("");
  }
  async function analyzeImage() {
    if(!image)return setError("Please select an image first.");
    setImageBusy(true);setError("");setMessage("");setImageReport(null);setImageReviewId(null);
    try {
      const form=new FormData();form.append("file",image);
      const d=await request("/analyze-image",{method:"POST",body:form});
      setImageReport(d);setImageReviewId(d.review_id);setImageDecision("Pending Review");await loadHistory();
    }catch(e){setError(e.message);}finally{setImageBusy(false);}
  }
  async function saveDecision(id,value,note,setValue) {
    if(!id)return setError("No saved review ID was returned.");
    try {
      await request(`/reviews/${id}/decision`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision:value,reviewer_note:note})});
      setValue(value);setMessage(`Final decision saved: ${value}`);await loadHistory();
    }catch(e){setError(e.message);}
  }
  async function deleteReview(id) {
    if(!window.confirm(`Delete review #${id}? This cannot be undone.`))return;
    try {
      await request(`/reviews/${id}`,{method:"DELETE"});
      setHistory(old=>old.filter(r=>r.id!==id));
      if(selectedReviewId===id)setSelectedReviewId(null);
      setMessage(`Review #${id} deleted.`);
    } catch(e){setError(e.message);}
  }
  async function clearHistory() {
    if(!window.confirm("Delete all saved content reviews? Brand guidelines will not be deleted."))return;
    try{await request("/reviews",{method:"DELETE"});setHistory([]);setSelectedReviewId(null);setMessage("Review history cleared.");}
    catch(e){setError(e.message);}
  }
  async function decideHistoryReview(id, decision) {
    try {
      await request(`/reviews/${id}/decision`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({decision,reviewer_note:historyReviewerNote})});
      setMessage(`Review #${id}: ${decision}.`);
      setHistoryReviewerNote("");
      await loadHistory();
    } catch(e){setError(e.message);}
  }
  function startNewGuideline(){setGuideline({...blankGuideline});setPendingLogo(null);setIsNewGuideline(true);setMessage("Enter details for the new brand profile.");setError("");}
  async function saveGuideline(event) {
    event.preventDefault();if(!guideline.brand_name.trim())return setError("Please enter a brand name.");
    setGuidelineSaving(true);setError("");setMessage("");
    try{
      const payload={...guideline,brand_name:guideline.brand_name.trim(),tone_of_voice:guideline.tone_of_voice.trim()};
      await request("/brand-guidelines",{method:isNewGuideline?"POST":"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      if(pendingLogo){const fd=new FormData();fd.append("file",pendingLogo);await request("/brand-guidelines/logo",{method:"POST",body:fd});setPendingLogo(null);}
      setIsNewGuideline(false);setMessage(isNewGuideline?"New brand profile saved and activated.":"Active brand profile updated.");
      await loadGuidelines();await loadGuidelineHistory();
    }catch(e){setError(e.message);}finally{setGuidelineSaving(false);}
  }
  function chooseLogo(event) {
    const file=event.target.files?.[0];if(!file)return;
    if(!["image/png","image/jpeg","image/webp"].includes(file.type)){setError("Choose a PNG, JPG or WebP logo.");event.target.value="";return;}
    if(file.size>2*1024*1024){setError("Logo must be smaller than 2 MB.");event.target.value="";return;}
    setPendingLogo(file);setError("");setMessage("Logo selected. Save the brand profile to upload it.");
  }
  async function removeLogo() {
    if(!window.confirm("Remove the logo from the active brand profile?"))return;
    try{await request("/brand-guidelines/logo",{method:"DELETE"});setGuideline(g=>({...g,logo_url:"",logo_filename:""}));setPendingLogo(null);setMessage("Brand logo removed.");}
    catch(e){setError(e.message);}
  }
  async function activateGuideline(id) {
    try{await request(`/brand-guidelines/${id}/activate`,{method:"POST"});setMessage("Brand profile activated.");await loadGuidelines();await loadGuidelineHistory();}
    catch(e){setError(e.message);}
  }
  function editField(field,value){setGuideline(old=>({...old,[field]:value}));}
  function statusPill(value) {
    const v=value||"Pending Review";const cls=v==="Approved"?"approved":v==="Rejected"?"rejected":v==="Revision Requested"?"revision":"pending";
    return <span className={`pill ${cls}`}>{v}</span>;
  }
  function issueTable(issues=[]) {
    if(!issues.length)return <div className="empty-success"><CheckCircle2/><div><b>No issues detected by the current rules.</b><span>Human review is still recommended before publication.</span></div></div>;
    return <div className="table-wrap"><table><thead><tr><th>Detected content</th><th>Brand rule</th><th>Severity</th><th>Explanation</th><th>Suggested correction</th></tr></thead><tbody>{issues.map((x,i)=><tr key={i}><td><b>{x.word||x.detected_text||"Issue"}</b></td><td>{x.rule||"Brand guideline"}</td><td><span className={`pill ${x.severity==="high"?"rejected":x.severity==="low"?"approved":"pending"}`}>{x.severity||"medium"}</span></td><td>{x.message||"This may not follow the active brand guidelines."}</td><td>{x.suggestion||"Replace with approved wording."}</td></tr>)}</tbody></table></div>;
  }
  function readabilityPanel(report) {
    if(!report)return <div className="empty">No readability data available for this saved analysis.</div>;
    return <div className="readability-grid">
      <div className="readability-stat"><b>{report.ocr_confidence ?? 0}%</b><span>OCR confidence</span></div>
      <div className="readability-stat"><b>{report.text_blocks ?? 0}</b><span>Text blocks</span></div>
      <div className="readability-stat"><b>{report.character_count ?? 0}</b><span>Characters</span></div>
      <div className="readability-stat"><b>{report.smallest_text_height_percent == null ? "—" : `${report.smallest_text_height_percent}%`}</b><span>Smallest text height estimate</span></div>
      <div className="readability-notes"><b>Findings</b><ul>{arr(report.findings).map((x,i)=><li key={i}>{x}</li>)}</ul><b>Suggested improvements</b><ul>{arr(report.suggestions).map((x,i)=><li key={i}>{x}</li>)}</ul><p className="muted">{report.note}</p></div>
    </div>;
  }
  function logoMatchPanel(match) {
    if(!match)return <div className="empty">No logo comparison data is available for this report.</div>;
    const status=match.status||"Not checked";
    const tone=status==="Likely match"?"approved":status==="Not detected"?"rejected":"pending";
    const nameCheck=match.brand_name_check;
    const nameTone=nameCheck?.status==="Match"?"approved":nameCheck?.status==="Possible mismatch"?"rejected":"pending";
    return <div className="logo-match-card">
      <div className="logo-match-top"><div><b>Official logo comparison</b><p className="muted">{match.method||"Visual comparison"}</p></div><span className={`pill ${tone}`}>{status}</span></div>
      <div className="logo-match-score"><strong>{Number(match.score||0)}%</strong><span>Visual similarity indicator · not a probability</span></div>
      <p>{match.note||"Review the poster logo manually."}</p>
      <div className="notice info" style={{marginTop:10}}>
        <b>Brand-name verification</b>
        <p><span className={`pill ${nameTone}`}>{nameCheck?.status||"Not checked"}</span></p>
        <p>Expected brand: {nameCheck?.expected_brand||"Not configured"}</p>
        {nameCheck?.detected_text&&<p>OCR evidence: {nameCheck.detected_text}</p>}
        <p>{nameCheck?.note||"No brand-name verification details are available."}</p>
      </div>
      {match.official_logo_filename&&<small className="muted">Compared with: {match.official_logo_filename}</small>}
      <p className="muted">Visual similarity and OCR brand-name checks are separate signals. Neither proves authenticity; a human reviewer makes the final decision.</p>
    </div>;
  }
  function reviewerPanel(id,value,setValue,note,setNote) {
    if(user?.role!=="manager")return <div className="notice info">Your submission is saved. A Brand Manager / Reviewer will make the final decision.</div>;
    return <div className="reviewer"><div><h3>Human review decision</h3><p>The AI flags possible issues. A human reviewer makes the final decision.</p></div>
      <textarea rows="2" placeholder="Reviewer note (optional)" value={note} onChange={e=>setNote(e.target.value)}/>
      <div className="actions">
        <button className="btn success" onClick={()=>saveDecision(id,"Approved",note,setValue)}><ThumbsUp size={16}/>Approve</button>
        <button className="btn warning" onClick={()=>saveDecision(id,"Revision Requested",note,setValue)}><RotateCcw size={16}/>Request revision</button>
        <button className="btn danger" onClick={()=>saveDecision(id,"Rejected",note,setValue)}><Ban size={16}/>Reject</button>{statusPill(value)}
      </div>
    </div>;
  }

  if(!user) return <div className="auth-page"><style>{styles}</style><div className="auth-card">
    <div className="auth-brand"><span className="brand-mark"><ShieldCheck size={25}/></span><div><b>BrandGuard AI</b><small>Intelligent Brand Governance</small></div></div>
    <h1>{authMode==="login"?"Welcome back":"Create your account"}</h1>
    <p className="auth-sub">{authMode==="login"?"Sign in to review and protect your brand.":"Register as a Content Creator. Manager access is restricted."}</p>
    {error&&<div className="notice err">{error}</div>}
    <form onSubmit={submitAuth}>
      {authMode==="register"&&<div className="field"><label>Full name</label><input required minLength="2" value={authName} onChange={e=>setAuthName(e.target.value)} placeholder="Your name"/></div>}
      <div className="field"><label>Email address</label><input required type="email" value={authEmail} onChange={e=>setAuthEmail(e.target.value)} placeholder="name@example.com"/></div>
      <div className="field"><label>Password</label><input required minLength="8" type="password" value={authPassword} onChange={e=>setAuthPassword(e.target.value)} placeholder="At least 8 characters"/></div>
      <button className="btn primary full" disabled={authBusy}>{authBusy?"Please wait...":authMode==="login"?"Sign in":"Create Content Creator account"}</button>
    </form>
    <p className="switch-auth">{authMode==="login"?"New to BrandGuard AI?":"Already registered?"} <button className="link-btn" onClick={()=>{setAuthMode(authMode==="login"?"register":"login");setError("");}}> {authMode==="login"?"Create an account":"Sign in"}</button></p>
    <div className="divider-text"><span>JUDGE DEMO ACCESS</span></div>
    <div className="demo-buttons"><button className="btn light" disabled={authBusy} onClick={()=>demoLogin("creator")}>Demo as Content Creator</button><button className="btn light" disabled={authBusy} onClick={()=>demoLogin("manager")}>Demo as Brand Manager</button></div>
    <small className="auth-foot">Demo accounts are for evaluation. Do not use demo credentials for private data.</small>
  </div></div>;

  const isManager=user.role==="manager";
  const nav=[["Dashboard",LayoutDashboard],["Content Review",FileSearch],...(isManager?[["Brand Guidelines",BookOpen]]:[]),["Review History",History]];
  const pendingCount=history.filter(r=>!r.decision||r.decision==="Pending Human Review").length;
  const totalIssues=history.reduce((n,r)=>n+Number(r.total_issues||0),0);

  return <div className="app-shell"><style>{styles}</style>
    <aside className="sidebar"><div className="brand"><span className="brand-mark"><ShieldCheck size={23}/></span>BrandGuard AI</div><div className="nav-label">WORKSPACE</div>
      <nav className="nav">{nav.map(([name,Icon])=><button key={name} className={page===name?"active":""} onClick={()=>{setPage(name);setMessage("");setError("");}}><Icon size={18}/>{name}</button>)}</nav>
      <div className="sidebar-foot">Brand governance workspace<br/>AI-assisted · Human-approved</div>
    </aside>
    <main className="main">
      <header className="topbar"><div><h1>{page}</h1><p className="sub">{page==="Dashboard"?"Monitor and protect your organisation's brand identity.":page==="Content Review"?"Check text and visual content before publishing.":page==="Brand Guidelines"?"Create and manage approved brand rules.":"Saved submissions and final reviewer decisions."}</p></div>
        <div className="top-actions"><span className="role-label">{isManager?"Brand Manager / Reviewer":"Content Creator"} · {user.name}</span>{page==="Content Review"&&<button className="btn light" onClick={newAnalysis}><Plus size={16}/>New Analysis</button>}<button className="btn light" onClick={()=>logout()}><LogOut size={15}/>Log out</button></div>
      </header>
      {message&&<div className="notice ok">{message}</div>}{error&&<div className="notice err">{error}</div>}
      {page==="Dashboard"&&<>
        <section className="hero"><h2>Protect your brand before you publish.</h2><p>Submit social posts, advertisements, emails, posters and flyers. BrandGuard AI checks content against active brand guidelines and supports human review.</p><button className="btn hero-btn" onClick={()=>setPage("Content Review")}><ScanSearch size={16}/>Start a content review</button></section>
        <div className="grid analytics-grid">
          <div className="stat"><div className="stat-icon"><FileText/></div><div><strong>{analytics?.total_reviews ?? history.length}</strong><span>Total submissions</span></div></div>
          <div className="stat"><div className="stat-icon"><AlertTriangle/></div><div><strong>{analytics?.total_issues ?? totalIssues}</strong><span>Issues detected</span></div></div>
          <div className="stat"><div className="stat-icon"><History/></div><div><strong>{analytics?.decisions?.Pending ?? pendingCount}</strong><span>Pending reviews</span></div></div>
          <div className="stat"><div className="stat-icon"><CheckCircle2/></div><div><strong>{analytics?.decisions?.Approved ?? 0}</strong><span>Approved</span></div></div>
          <div className="stat"><div className="stat-icon"><Ban/></div><div><strong>{analytics?.decisions?.Rejected ?? 0}</strong><span>Rejected</span></div></div>
          <div className="stat"><div className="stat-icon"><RotateCcw/></div><div><strong>{analytics?.decisions?.["Revision Requested"] ?? 0}</strong><span>Revision requested</span></div></div>
        </div>
        <section className="panel analytics-panel"><div className="panel-head"><div><h2>Submission analytics</h2><p>{isManager?"Team-wide review activity.":"Your submission activity."} Counts update when history is refreshed.</p></div><button className="btn light" onClick={loadAnalytics}><RefreshCw size={15}/>{analyticsBusy?"Updating...":"Refresh analytics"}</button></div>
          <div className="analytics-columns">
            <div><h3>Decision breakdown</h3>{["Pending","Approved","Revision Requested","Rejected"].map(k=>{const n=analytics?.decisions?.[k]||0;const max=Math.max(1,...Object.values(analytics?.decisions||{}));return <div className="metric-row" key={k}><span>{k}</span><div className="metric-track"><i style={{width:`${n/max*100}%`}}/></div><b>{n}</b></div>;})}</div>
            <div><h3>Content type</h3>{["Text","Image"].map(k=>{const n=analytics?.content_types?.[k]||0;const max=Math.max(1,...Object.values(analytics?.content_types||{}));return <div className="metric-row" key={k}><span>{k==="Image"?"Posters / flyers":"Text"}</span><div className="metric-track"><i style={{width:`${n/max*100}%`}}/></div><b>{n}</b></div>;})}
              <h3 style={{marginTop:18}}>Issue severity</h3>{["high","medium","low"].map(k=><div className="metric-row" key={k}><span>{k[0].toUpperCase()+k.slice(1)}</span><div className="metric-track"><i style={{width:`${(analytics?.severity?.[k]||0)/Math.max(1,analytics?.total_issues||0)*100}%`}}/></div><b>{analytics?.severity?.[k]||0}</b></div>)}</div>
          </div>
          <p className="muted">{analytics?.daily_reviews?.length?`Recent activity: ${analytics.daily_reviews.map(x=>`${x.date}: ${x.count}`).join(" · ")}`:"No submission activity yet."}</p>
        </section>
        <section className="panel"><div className="panel-head"><div><h2>Recent reviews</h2><p>Latest saved submissions</p></div><button className="btn light" onClick={()=>setPage("Review History")}>View history</button></div>
          {history.slice(0,5).length?<div className="table-wrap"><table className="history-table"><thead><tr><th>ID</th><th>Type</th><th>Submitted content</th><th>Issues</th><th>Final decision</th></tr></thead><tbody>{history.slice(0,5).map(r=><tr key={r.id}><td>#{r.id}</td><td>{r.type}</td><td>{r.type==="Image"?r.image_filename:(r.submitted_content||"").slice(0,100)}</td><td>{r.total_issues}</td><td>{statusPill(r.decision)}</td></tr>)}</tbody></table></div>:<div className="empty">No reviews saved yet. Start by analysing content.</div>}
        </section>
      </>}
      {page==="Content Review"&&<>
        <section className="panel"><div className="panel-head"><div><h2>Submit content for review</h2><p>Choose text or upload a poster, flyer or screenshot. Each new submission starts a fresh report.</p></div><ScanSearch color="#0f766e" size={25}/></div>
          <div className="split"><div><h3>1. Analyse typed content</h3><div className="field"><textarea placeholder="Paste a social media post, advertisement, email or other brand content..." value={text} onChange={e=>{if(textReport&&e.target.value!==text){setTextReport(null);setTextReviewId(null);setImage(null);setImageReport(null);setImageReviewId(null);if(fileRef.current)fileRef.current.value="";}setText(e.target.value);}}/></div><div className="inline"><span className="muted">{text.length} characters</span><button className="btn primary" disabled={busy} onClick={analyzeText}><ScanSearch size={16}/>{busy?"Analysing...":"Analyse text"}</button></div></div>
          <div><h3>2. Analyse an image</h3><label className="upload"><UploadCloud size={27}/><b>Choose poster, flyer or screenshot</b><small>JPG, PNG or WebP · Maximum 5 MB<input ref={fileRef} type="file" accept="image/png,image/jpeg,image/webp" onChange={chooseImage}/></small></label>
            {image&&<div className="fileline"><span>{image.name} · {(image.size/1024).toFixed(1)} KB</span><button className="btn light" onClick={()=>{setImage(null);setImageReport(null);if(fileRef.current)fileRef.current.value="";}}>Remove</button></div>}
            <div style={{marginTop:12}}><button className="btn primary" disabled={!image||imageBusy} onClick={analyzeImage}><ScanSearch size={16}/>{imageBusy?"Reading image...":"Analyse image"}</button></div></div></div>
        </section>
        {textReport&&<section className="panel"><div className="report-head"><div><h2>Text compliance report</h2><p>Automated analysis · Review ID #{textReviewId}</p></div><span className="pill pending">{textReport.total_issues?"Needs attention":"Basic checks passed"}</span></div>
          <div className="score-row"><div className="score">{textReport.score}<small>/100</small></div><div style={{flex:1}}><b>Basic compliance score</b><p className="muted">{textReport.total_issues} issue(s) detected</p><div className="bar"><span style={{width:`${textReport.score}%`}}/></div></div></div>
          {issueTable(arr(textReport.issues))}{reviewerPanel(textReviewId,textDecision,setTextDecision,textNote,setTextNote)}</section>}
        {imageReport&&<section className="panel"><div className="report-head"><div><h2>Image compliance report</h2><p>{imageReport.filename||image?.name} · OCR analysis · Review ID #{imageReviewId}</p></div><span className="pill pending">{imageReport.total_issues?"Needs attention":"Basic checks passed"}</span></div>
          <h3>Text extracted from image (OCR)</h3><div className="ocr">{imageReport.extracted_text||"No text detected. Try a clearer, higher-resolution image."}</div>
          <h3>Official logo check</h3>{logoMatchPanel(imageReport.readability?.logo_match)}
          <h3>Poster / flyer readability analysis</h3><p className="muted">OCR method: {imageReport.ocr_method||"Enhanced OCR"}</p>{readabilityPanel(imageReport.readability)}
          <h3>Detected brand issues</h3>{issueTable(arr(imageReport.issues))}
          {reviewerPanel(imageReviewId,imageDecision,setImageDecision,imageNote,setImageNote)}<p className="muted" style={{marginTop:12}}>Readability results are automated estimates. Please verify the original image, especially small text, contrast and OCR accuracy.</p></section>}
      </>}
      {page==="Brand Guidelines"&&isManager&&<>
        <section className="panel"><div className="panel-head"><div><h2>{isNewGuideline?"Add a new brand profile":"Active brand profile"}</h2><p>{isNewGuideline?"Saving creates a separate profile and activates it.":"These rules are used by the compliance checker."}</p></div><button className="btn primary" onClick={startNewGuideline}><Plus size={16}/>Add New Brand Guideline</button></div>
          {guidelineBusy?<div className="empty">Loading brand guidelines...</div>:<form onSubmit={saveGuideline}>
            <div className="field"><label>Brand name</label><textarea rows="2" value={guideline.brand_name} onChange={e=>editField("brand_name",e.target.value)} placeholder="e.g. GreenBite Food or GreenBite\nFOODS"/></div>
            <div className="field"><label>Brand logo (optional)</label><div className="logo-upload-row">{guideline.logo_url&&!pendingLogo?<img className="brand-logo-preview" src={guideline.logo_url} alt="Current brand logo"/>:pendingLogo?<div className="brand-logo-placeholder">{pendingLogo.name}</div>:<div className="brand-logo-placeholder">No logo uploaded</div>}<div className="logo-actions"><label className="btn light">{guideline.logo_url||pendingLogo?"Replace logo":"Upload logo"}<input type="file" accept="image/png,image/jpeg,image/webp" onChange={chooseLogo} hidden/></label>{(guideline.logo_url||pendingLogo)&&<button type="button" className="btn danger" onClick={()=>{if(pendingLogo){setPendingLogo(null);}else{removeLogo();}}}>Remove</button>}<small className="muted">PNG, JPG or WebP · Maximum 2 MB. The logo is stored with this brand profile.</small></div></div></div>
            <div className="field"><label>Tone of voice</label><textarea rows="3" value={guideline.tone_of_voice} onChange={e=>editField("tone_of_voice",e.target.value)} placeholder="Professional, friendly and trustworthy"/></div>
            <div className="split"><div className="field"><label>Approved brand colours (one per line)</label><textarea rows="4" value={guideline.approved_colors.join("\n")} onChange={e=>editField("approved_colors",lines(e.target.value))} placeholder="#0F766E&#10;#172554&#10;#FFFFFF"/></div><div className="field"><label>Restricted terms (one per line)</label><textarea rows="4" value={guideline.restricted_terms.join("\n")} onChange={e=>editField("restricted_terms",lines(e.target.value))} placeholder="guaranteed&#10;100% free"/></div></div>
            <div className="field"><label>Approved claims / phrases (one per line)</label><textarea rows="3" value={guideline.approved_claims.join("\n")} onChange={e=>editField("approved_claims",lines(e.target.value))} placeholder="Quality products"/></div>
            <div className="field"><label>Preferred terminology (one mapping per line: old term -&gt; preferred term)</label><textarea rows="3" value={guideline.approved_terms.join("\n")} onChange={e=>editField("approved_terms",lines(e.target.value))} placeholder="clients -&gt; customers&#10;cheap -&gt; affordable"/><small className="muted">The checker flags the old term and suggests the preferred wording.</small></div>
            <div className="field"><label>Required brand terms or phrases (one per line)</label><textarea rows="3" value={guideline.required_terms.join("\n")} onChange={e=>editField("required_terms",lines(e.target.value))} placeholder="Official brand name&#10;Approved campaign tagline"/><small className="muted">Use only when the phrase genuinely needs to appear in every type of content being checked.</small></div>
            <div className="field"><label>Verified brand facts (one approved fact per line)</label><textarea rows="4" value={guideline.brand_facts.join("\n")} onChange={e=>editField("brand_facts",lines(e.target.value))} placeholder="Founded in 2018&#10;Head office is in Hyderabad&#10;Certified under ISO 9001"/><small className="muted">Use facts that have been verified by your organisation. The checker uses these as context when flagging factual claims.</small></div>
            <div className="inline"><button className="btn primary" type="submit" disabled={guidelineSaving}><BookOpen size={16}/>{guidelineSaving?"Saving...":isNewGuideline?"Save and activate new profile":"Save changes"}</button>{isNewGuideline&&<button type="button" className="btn light" onClick={loadGuidelines}>Cancel</button>}</div>
          </form>}</section>
        <section className="panel"><div className="panel-head"><div><h2>Brand guideline history</h2><p>Previous profiles are kept. Activate one to use its rules.</p></div><button className="btn light" onClick={loadGuidelineHistory}><RefreshCw size={15}/>Refresh</button></div>
          {guidelineHistory.length?<div className="table-wrap"><table className="history-table"><thead><tr><th>Profile ID</th><th>Brand name</th><th>Tone</th><th>Created</th><th>Status</th><th>Action</th></tr></thead><tbody>{guidelineHistory.map(g=><tr key={g.id}><td>#{g.id}</td><td>{g.brand_name}</td><td>{g.tone_of_voice||"—"}</td><td>{dateText(g.created_at)}</td><td>{g.is_active?"Active":"Saved"}</td><td>{g.is_active?"Currently active":<button className="btn light" onClick={()=>activateGuideline(g.id)}><Power size={14}/>Activate</button>}</td></tr>)}</tbody></table></div>:<div className="empty">No guideline versions found.</div>}
        </section>
      </>}
      {page==="Review History"&&<section className="panel"><div className="panel-head"><div><h2>Saved content reviews</h2><p>{isManager?"All team submissions and final reviewer decisions.":"Your saved submissions and their review status."}</p></div><div className="inline"><button className="btn light" onClick={loadHistory}><RefreshCw size={15}/>Refresh</button>{isManager&&<button className="btn danger" onClick={clearHistory}><Trash2 size={15}/>Clear History</button>}</div></div>
        {historyBusy?<div className="empty">Loading review history...</div>:history.length?<div className="table-wrap"><table className="history-table"><thead><tr><th>Review ID / Type</th><th>Submitted content</th><th>Date</th><th>Issues</th><th>Final decision</th><th>Actions</th></tr></thead><tbody>{history.map(r=><tr key={r.id}><td>#{r.id}<br/><span className="muted">{r.type}</span></td><td>{r.type==="Image"?(r.image_filename||"Uploaded image"):(r.submitted_content||"").slice(0,180)}</td><td>{dateText(r.date)}</td><td>{r.total_issues}</td><td>{statusPill(r.decision)}</td><td><div className="actions"><button className="btn light" onClick={()=>{setSelectedReviewId(selectedReviewId===r.id?null:r.id);setHistoryReviewerNote(r.reviewer_note||"");}}>{selectedReviewId===r.id?"Close":"Review details"}</button><button className="btn danger" onClick={()=>deleteReview(r.id)}><Trash2 size={14}/>Delete</button></div></td></tr>)}</tbody></table></div>:<div className="empty"><History size={30}/><p>No saved reviews yet.</p></div>}
        {selectedReviewId && (()=>{const r=history.find(x=>x.id===selectedReviewId);if(!r)return null;return <section className="history-detail"><div className="panel-head"><div><h2>Review #{r.id} · {r.type}</h2><p>Submitted {dateText(r.date)} · {r.total_issues} detected issue(s)</p></div>{statusPill(r.decision)}</div>
          {r.type==="Image"&&<><h3>Official logo check</h3>{logoMatchPanel(r.readability?.logo_match)}<h3>Poster / flyer readability analysis</h3>{readabilityPanel(r.readability)}<h3>Extracted text (OCR)</h3><div className="ocr">{r.extracted_text||"No text was detected."}</div></>}
          {r.type!=="Image"&&<><h3>Submitted content</h3><div className="ocr">{r.submitted_content}</div></>}
          <h3>Detected brand issues</h3>{issueTable(arr(r.issues))}
          <h3>Reviewer note</h3><div className="ocr">{r.reviewer_note||"No reviewer note saved."}</div>
          {isManager&&<div className="reviewer"><h3>Make / update final decision</h3><textarea rows="2" placeholder="Add a reviewer note (optional)" value={historyReviewerNote} onChange={e=>setHistoryReviewerNote(e.target.value)}/><div className="actions"><button className="btn success" onClick={()=>decideHistoryReview(r.id,"Approved")}><ThumbsUp size={15}/>Approve</button><button className="btn warning" onClick={()=>decideHistoryReview(r.id,"Revision Requested")}><RotateCcw size={15}/>Request revision</button><button className="btn danger" onClick={()=>decideHistoryReview(r.id,"Rejected")}><Ban size={15}/>Reject</button></div></div>}
        </section>;})()}
      </section>}
    </main>
  </div>;
}

const styles = `
*{box-sizing:border-box}body{margin:0;background:#f3f6fb;font-family:Inter,Segoe UI,Arial,sans-serif;color:#172554}button,input,textarea{font:inherit}
.app-shell{min-height:100vh;display:flex;background:#f3f6fb}.sidebar{width:245px;background:#142344;color:#fff;padding:26px 16px;display:flex;flex-direction:column;flex-shrink:0}
.brand{display:flex;align-items:center;gap:11px;padding:0 10px 28px;font-size:18px;font-weight:800}.brand-mark{width:38px;height:38px;border-radius:12px;background:#0f766e;display:grid;place-items:center;color:white}
.nav-label{font-size:10px;letter-spacing:1.5px;color:#9eacc6;padding:10px 12px}.nav button{border:0;background:transparent;color:#cbd5e1;width:100%;padding:12px;border-radius:9px;text-align:left;display:flex;gap:12px;align-items:center;margin:3px 0;cursor:pointer}
.nav button.active,.nav button:hover{background:#263b60;color:#fff}.sidebar-foot{margin-top:auto;padding:15px 10px;color:#9eacc6;font-size:12px;line-height:1.6}
.main{flex:1;min-width:0;padding:30px 34px;max-width:1500px;margin:0 auto;width:100%}.topbar{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:25px}
h1{font-size:25px;margin:0 0 5px;color:#172554}.sub{margin:0;color:#64748b;font-size:13px}.top-actions{display:flex;gap:9px;flex-wrap:wrap;align-items:center}.role-label{font-size:11px;color:#0f766e;background:#e2f5f1;padding:8px 10px;border-radius:20px;font-weight:700}
.btn{border:0;border-radius:8px;padding:10px 14px;display:inline-flex;align-items:center;justify-content:center;gap:8px;font-weight:650;font-size:13px;cursor:pointer}.btn:disabled{opacity:.55;cursor:not-allowed}
.primary{background:#0f766e;color:white}.light{background:#e7edf5;color:#243653}.danger{background:#fee2e2;color:#991b1b}.success{background:#dcfce7;color:#166534}.warning{background:#fef3c7;color:#92400e}
.notice{padding:12px 15px;border-radius:9px;margin:0 0 16px;font-size:13px}.notice.ok{background:#dcfce7;color:#166534}.notice.err{background:#fee2e2;color:#991b1b}.notice.info{background:#eaf2ff;color:#24456e}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-bottom:20px}.stat,.panel{background:#fff;border:1px solid #e5eaf1;border-radius:13px;padding:20px;box-shadow:0 2px 8px #17255408}.stat{display:flex;align-items:center;gap:14px}.stat-icon{width:42px;height:42px;border-radius:11px;background:#e5f4f2;color:#0f766e;display:grid;place-items:center}.stat strong{font-size:23px;display:block}.stat span{font-size:12px;color:#64748b}
.panel{margin-bottom:18px}.panel-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:17px}.panel h2{font-size:17px;margin:0 0 5px}.panel h3{font-size:14px;margin:0 0 8px}.panel p{font-size:13px;color:#64748b;margin:0;line-height:1.5}
textarea,input{width:100%;border:1px solid #d8e0eb;border-radius:8px;padding:12px;color:#172554;background:#fff;outline:none}textarea:focus,input:focus{border-color:#0f766e;box-shadow:0 0 0 3px #0f766e15}textarea{resize:vertical;min-height:125px}
.split{display:grid;grid-template-columns:1fr 1fr;gap:18px}.field{margin-bottom:15px}.field label{display:block;font-size:12px;font-weight:700;margin-bottom:7px;color:#334155}.inline{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.muted{color:#64748b;font-size:12px}
.upload{border:1.5px dashed #b7c6d6;background:#f8fafc;border-radius:11px;padding:23px;text-align:center;display:block;cursor:pointer;color:#0f766e}.upload input{display:none}.upload b{display:block;margin:8px 0 4px;color:#243653}.upload small{color:#64748b}
.fileline{display:flex;align-items:center;justify-content:space-between;background:#f1f5f9;padding:10px;border-radius:8px;margin-top:10px;font-size:12px;gap:8px}
.hero{background:linear-gradient(120deg,#172554,#0f766e);color:#fff;border-radius:14px;padding:26px;margin-bottom:18px}.hero h2{font-size:21px;margin:0 0 8px}.hero p{color:#d8e8ee;max-width:650px}.hero-btn{margin-top:18px;background:white;color:#0f766e}
.report-head{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:15px}.report-head h2{margin:0}.pill{display:inline-flex;align-items:center;border-radius:20px;padding:6px 10px;font-size:11px;font-weight:750;white-space:nowrap}.pending{background:#f1f5f9;color:#475569}.approved{background:#dcfce7;color:#166534}.rejected{background:#fee2e2;color:#991b1b}.revision{background:#fef3c7;color:#92400e}
.score-row{display:flex;gap:15px;align-items:center;background:#f8fafc;border-radius:10px;padding:15px;margin-bottom:16px}.score{font-size:30px;font-weight:800;color:#0f766e}.score small{font-size:12px;color:#64748b}.bar{height:7px;background:#e2e8f0;border-radius:9px;overflow:hidden;margin-top:9px}.bar>span{display:block;height:100%;background:#0f766e}
.table-wrap{overflow:auto;border:1px solid #e5eaf1;border-radius:9px;margin:12px 0}.table-wrap table{width:100%;border-collapse:collapse;min-width:650px;font-size:12px}.table-wrap th{background:#f1f5f9;text-align:left;color:#475569;font-size:11px}.table-wrap th,.table-wrap td{padding:11px 12px;border-bottom:1px solid #e8edf3;vertical-align:top}.table-wrap tr:last-child td{border-bottom:0}
.empty-success{display:flex;align-items:center;gap:12px;background:#f0fdf4;border-radius:9px;padding:15px;color:#166534;margin:12px 0}.empty-success span{display:block;font-size:12px;margin-top:4px;color:#4b7b5a}.reviewer{border-top:1px solid #e8edf3;margin-top:17px;padding-top:16px;display:grid;gap:11px}.reviewer h3{margin:0 0 4px}.reviewer textarea{min-height:60px}.actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.ocr{background:#f8fafc;border:1px solid #e5eaf1;padding:13px;border-radius:8px;white-space:pre-wrap;font-size:13px;line-height:1.6;margin:12px 0}.history-table{width:100%;border-collapse:collapse;min-width:760px;font-size:12px}.history-table th{background:#f1f5f9;color:#475569;text-align:left}.history-table th,.history-table td{padding:12px;border-bottom:1px solid #e8edf3;vertical-align:top}.empty{padding:35px;text-align:center;color:#64748b}
.readability-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin:12px 0 18px}.readability-stat{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:9px;padding:12px}.readability-stat b{display:block;font-size:20px;color:#0f766e}.readability-stat span{font-size:11px;color:#64748b}.readability-notes{grid-column:1/-1;background:#f8fafc;border:1px solid #e2e8f0;border-radius:9px;padding:14px;font-size:13px}.readability-notes ul{margin:7px 0 13px;padding-left:20px;color:#475569}.history-detail{margin-top:20px;padding:18px;background:#fbfdff;border:1px solid #dbe5ef;border-radius:11px}.history-detail h3{margin:15px 0 8px;font-size:14px}.auth-page{min-height:100vh;background:linear-gradient(135deg,#eaf0f8,#f4f8fb);display:grid;place-items:center;padding:22px}.auth-card{width:min(100%,470px);background:white;padding:34px;border:1px solid #e2e8f0;border-radius:18px;box-shadow:0 18px 60px #17255418}.auth-brand{display:flex;align-items:center;gap:12px;margin-bottom:28px}.auth-brand b,.auth-brand small{display:block}.auth-brand small{font-size:11px;color:#64748b;margin-top:4px}.auth-card h1{font-size:25px}.auth-sub{font-size:13px;color:#64748b;margin:8px 0 22px}.full{width:100%;margin-top:4px}.switch-auth{text-align:center;font-size:12px;color:#64748b;margin-top:18px}.link-btn{border:0;background:none;color:#0f766e;font-weight:700;cursor:pointer}.divider-text{display:flex;align-items:center;gap:12px;color:#94a3b8;font-size:10px;font-weight:800;letter-spacing:1px;margin:25px 0 14px}.divider-text:before,.divider-text:after{content:"";height:1px;background:#e2e8f0;flex:1}.demo-buttons{display:grid;grid-template-columns:1fr 1fr;gap:9px}.demo-buttons button{font-size:11px;padding:11px 7px}.auth-foot{display:block;text-align:center;color:#94a3b8;font-size:10px;margin-top:16px}
@media(max-width:850px){.sidebar{width:190px}.main{padding:22px 18px}.grid{grid-template-columns:1fr 1fr}.split{grid-template-columns:1fr}}
@media(max-width:600px){.readability-grid{grid-template-columns:1fr 1fr}.app-shell{display:block}.sidebar{width:100%;padding:14px}.brand{padding-bottom:12px}.nav{display:flex;overflow:auto}.nav-label,.sidebar-foot{display:none}.nav button{white-space:nowrap;width:auto}.main{padding:18px 12px}.grid{grid-template-columns:1fr}.topbar{align-items:flex-start;flex-direction:column}.demo-buttons{grid-template-columns:1fr}.auth-card{padding:24px}}

.analytics-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.analytics-columns{display:grid;grid-template-columns:1fr 1fr;gap:28px}.metric-row{display:grid;grid-template-columns:130px 1fr 30px;align-items:center;gap:10px;margin:12px 0;font-size:13px}.metric-track{height:9px;background:#e8eef2;border-radius:99px;overflow:hidden}.metric-track i{display:block;height:100%;background:#0f766e;border-radius:99px}.logo-match-card{border:1px solid #dbe5ec;border-radius:12px;padding:16px;margin:10px 0 18px;background:#fbfdff}.logo-match-top{display:flex;align-items:center;justify-content:space-between;gap:12px}.logo-match-top p{margin:4px 0}.logo-match-score{display:flex;align-items:baseline;gap:10px;margin:12px 0}.logo-match-score strong{font-size:28px;color:#0f766e}.logo-match-score span{font-size:12px;color:#64748b}.logo-match-card>p{font-size:13px;line-height:1.5}.logo-upload-row{display:flex;align-items:center;gap:16px;flex-wrap:wrap}.brand-logo-preview{width:112px;height:88px;object-fit:contain;border:1px solid #dbe3e8;border-radius:12px;padding:8px;background:#fff}.brand-logo-placeholder{width:112px;height:88px;display:grid;place-items:center;text-align:center;padding:8px;border:1px dashed #aab8c2;border-radius:12px;color:#64748b;font-size:12px;overflow-wrap:anywhere}.logo-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.logo-actions small{flex-basis:100%}@media(max-width:760px){.analytics-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.analytics-columns{grid-template-columns:1fr}.metric-row{grid-template-columns:105px 1fr 24px}}
`;
