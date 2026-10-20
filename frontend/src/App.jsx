
import { useEffect, useState } from "react";
import "./App.css";

const API_BASE = "http://127.0.0.1:8000";

const BENCHMARK_CASES = [
  {
    prompt:
      "Return the company name and employee count as JSON. Use only the supplied source.",
    source_content:
      "Acme Technologies uses Python and has 150 employees.",
    expected_schema: {
      type: "object",
      properties: {
        company: { type: "string" },
        employee_count: { type: "integer" },
      },
      required: ["company", "employee_count"],
      additionalProperties: false,
    },
  },
  {
    prompt:
      "Return the technology and employee count as JSON. Use only the supplied source.",
    source_content:
      "Acme Technologies uses Python and has 150 employees.",
    expected_schema: {
      type: "object",
      properties: {
        technology: { type: "string" },
        employee_count: { type: "integer" },
      },
      required: ["technology", "employee_count"],
      additionalProperties: false,
    },
  },
];

function formatPercent(value) {
  return value == null || !Number.isFinite(Number(value))
    ? "—"
    : `${Number(value).toFixed(1)}%`;
}

function formatLatency(value) {
  return value == null || !Number.isFinite(Number(value))
    ? "—"
    : `${(Number(value) / 1000).toFixed(2)} s`;
}

function shortenPrompt(value, maxLength = 140) {
  const promptText = String(value || "Prompt not available").replace(/\s+/g, " ").trim();
  return promptText.length > maxLength
    ? `${promptText.slice(0, maxLength).trimEnd()}…`
    : promptText;
}

function formatResponse(value) {
  if (value == null || value === "") {
    return "No response returned";
  }

  if (typeof value === "string") {
    return value;
  }

  return JSON.stringify(value, null, 2);
}

function observedLimitation(modelName, results) {
  const rows = (results || []).filter((item) => item.model === modelName);
  if (!rows.length) return "No benchmark evidence yet. Run the same test suite against both models to record an observed limitation.";
  if (rows.some((item) => item.failure_type === "execution_error")) return "An execution error occurred for this model in the selected benchmark run. Check Ollama model availability and the recorded error.";
  if (rows.some((item) => item.schema_valid === false)) return "At least one response failed JSON Schema validation in the selected benchmark run.";
  if (rows.some((item) => (item.evidence_findings || []).some((finding) => finding.classification === "unsupported"))) return "At least one response contained a claim the source-based heuristic could not support in the selected benchmark run.";
  if (rows.some((item) => (item.contradictions || []).length > 0)) return "At least one response had a potential source contradiction in the selected benchmark run.";
  return "No schema or source-evidence failure was flagged in this run. This limited sample does not prove factual correctness.";
}

function AppIcon({ name, size = 18 }) {
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
    focusable: false,
  };
  const paths = {
    debugger: <><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 9h8M8 12h5M8 15h3" /></>,
    overview: <><rect x="3.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.5" /><rect x="3.5" y="13.5" width="7" height="7" rx="1.5" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.5" /></>,
    benchmarks: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2" /></>,
    history: <><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></>,
    failures: <><path d="m12 3 9 16H3L12 3Z" /><path d="M12 9v4M12 16h.01" /></>,
    disclosure: <><circle cx="12" cy="12" r="9" /><path d="M9.7 9a2.4 2.4 0 1 1 4.1 1.7c-1.2 1.1-1.8 1.3-1.8 2.8M12 17h.01" /></>,
    upload: <><path d="M12 16V4M7 9l5-5 5 5" /><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" /></>,
    download: <><path d="M12 4v12M7 11l5 5 5-5" /><path d="M4 20h16" /></>,
    file: <><path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10Z" /><path d="M13 3v7h7M8 14h8M8 17h8" /></>,
    plus: <><path d="M12 5v14M5 12h14" /></>,
  };
  return <svg {...common}>{paths[name] || paths.file}</svg>;
}

function StatusBadge({ passed, label }) {
  return (
    <span
      className={`evidence-badge ${
        passed ? "supported" : "unsupported"
      }`}
    >
      {label}
    </span>
  );
}

function ScoreCard({ label, score }) {
  const numericScore = Number(score);
  const validScore =
    score != null && Number.isFinite(numericScore);

  const width = validScore
    ? Math.max(0, Math.min(100, numericScore))
    : 0;

  return (
    <div className="score-card">
      <span>{label}</span>
      <strong>{validScore ? `${numericScore.toFixed(1)}%` : "—"}</strong>
      <div className="score-track">
        <div
          className="score-fill"
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function App() {
  const [activePage, setActivePage] = useState("debugger");
  const [historySearch, setHistorySearch] = useState("");
  const [failureSearch, setFailureSearch] = useState("");
  const [historyStatus, setHistoryStatus] = useState("all");
  const [benchmarkModels, setBenchmarkModels] = useState(["qwen3:4b", "llama3.2:3b"]);
  const [selectedExecutionId, setSelectedExecutionId] = useState(null);

  // Single-prompt execution
  const [prompt, setPrompt] = useState("");
  const [sourceContent, setSourceContent] = useState("");
  const [schemaText, setSchemaText] = useState(
    '{\n  "type": "object",\n  "properties": {\n    "answer": { "type": "string" }\n  },\n  "required": ["answer"]\n}'
  );
  
  const [model, setModel] = useState("llama3.2:3b");
  const [fallbackModel, setFallbackModel] = useState("qwen3:4b");
  const [maxRetries, setMaxRetries] = useState(2);

  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Document upload and downloadable validation report
  const [selectedFile, setSelectedFile] = useState(null);
  const [documentLoading, setDocumentLoading] = useState(false);
  const [documentError, setDocumentError] = useState("");
  const [reportLoading, setReportLoading] = useState(false);

  // Model benchmarking
  // Benchmark runs are persisted by the FastAPI backend in SQLite.
  const [benchmarkRunHistory, setBenchmarkRunHistory] = useState([]);
  const [benchmarkResult, setBenchmarkResult] = useState(null);
  const [benchmarkLoading, setBenchmarkLoading] = useState(false);
  const [benchmarkError, setBenchmarkError] = useState("");

  // Persistent execution and failure history
  const [executionHistory, setExecutionHistory] = useState([]);
  const [failureHistory, setFailureHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [visibleExecutions, setVisibleExecutions] = useState(5);
  const [visibleFailures, setVisibleFailures] = useState(5);

  useEffect(() => {
    loadHistory();
    loadBenchmarkHistory();
  }, []);

  async function loadHistory() {
    setHistoryLoading(true);
    setHistoryError("");

    try {
      const [historyResponse, failuresResponse] = await Promise.all([
        fetch(`${API_BASE}/api/executions?limit=100`),
        fetch(`${API_BASE}/api/failures?limit=100`),
      ]);

      const historyData = await historyResponse.json();
      const failuresData = await failuresResponse.json();

      if (!historyResponse.ok) {
        throw new Error(
          historyData.detail || "Could not load execution history."
        );
      }
      if (!failuresResponse.ok) {
        throw new Error(
          failuresData.detail || "Could not load failure history."
        );
      }

      setExecutionHistory(historyData.executions || []);
      setFailureHistory(failuresData.failures || []);
      setVisibleExecutions(5);
      setVisibleFailures(5);
    } catch (err) {
      setHistoryError(
        err.message.includes("Failed to fetch")
          ? "Cannot connect to FastAPI while loading history."
          : err.message
      );
    } finally {
      setHistoryLoading(false);
    }
  }


  async function loadBenchmarkHistory() {
    try {
      const response = await fetch(`${API_BASE}/api/benchmarks?limit=20`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not load benchmark history.");
      setBenchmarkRunHistory(data.runs || []);
      return data.runs || [];
    } catch (err) {
      setBenchmarkError(err.message.includes("Failed to fetch")
        ? "Cannot connect to FastAPI while loading saved benchmarks."
        : err.message);
      return [];
    }
  }

  async function openBenchmark(runId) {
    setBenchmarkError("");
    try {
      const response = await fetch(`${API_BASE}/api/benchmark/${encodeURIComponent(runId)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Could not load benchmark details.");
      setBenchmarkResult(data);
    } catch (err) {
      setBenchmarkError(err.message);
    }
  }

  async function openExecution(executionId) {
    setHistoryError("");

    try {
      const response = await fetch(
        `${API_BASE}/api/execution/${encodeURIComponent(executionId)}`
      );
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Could not load execution details.");
      }

      setResult(data);
      setSelectedExecutionId(executionId);
      setActivePage("debugger");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      setHistoryError(err.message);
    }
  }

  async function executePrompt() {
    setError("");
    setResult(null);

    if (!prompt.trim()) {
      setError("Please enter a prompt first.");
      return;
    }

    let expectedSchema = null;

    if (schemaText.trim()) {
      try {
        expectedSchema = JSON.parse(schemaText);
      } catch {
        setError("Your expected JSON schema is not valid JSON.");
        return;
      }
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/execute`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          prompt: prompt.trim(),
          source_content: sourceContent.trim() || null,
          expected_schema: expectedSchema,
          model,
          fallback_model: fallbackModel || null,
          max_retries: Number(maxRetries),
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail || "Request failed.")
        );
      }

      setResult(data);
      await loadHistory();
    } catch (err) {
      setError(
        err.message.includes("Failed to fetch")
          ? "Cannot connect to FastAPI. Confirm the backend is running and CORS is configured."
          : err.message
      );
    } finally {
      setLoading(false);
    }
  }

  async function executeDocument() {
    setDocumentError("");
    setError("");
    setResult(null);

    if (!selectedFile) {
      setDocumentError("Choose a TXT or PDF document first.");
      return;
    }
    if (!prompt.trim()) {
      setDocumentError("Enter a prompt describing what to extract or validate from the document.");
      return;
    }

    let expectedSchema = null;
    if (schemaText.trim()) {
      try {
        expectedSchema = JSON.parse(schemaText);
      } catch {
        setDocumentError("Your expected JSON schema is not valid JSON.");
        return;
      }
    }

    const formData = new FormData();
    formData.append("prompt", prompt.trim());
    formData.append("file", selectedFile);
    if (expectedSchema) formData.append("expected_schema_json", JSON.stringify(expectedSchema));
    formData.append("model", model);
    if (fallbackModel) formData.append("fallback_model", fallbackModel);
    formData.append("max_retries", String(Number(maxRetries)));

    setDocumentLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/execute-document`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || "Document validation failed."));
      }
      setResult(data);
      setSelectedExecutionId(data.execution_id || null);
      await loadHistory();
    } catch (err) {
      setDocumentError(err.message.includes("Failed to fetch")
        ? "Cannot connect to FastAPI. Confirm the backend is running and CORS is configured."
        : err.message);
    } finally {
      setDocumentLoading(false);
    }
  }

  async function downloadValidationReport(executionId) {
    if (!executionId) {
      setDocumentError("No execution ID is available for this report.");
      return;
    }
    setDocumentError("");
    setReportLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/execution/${encodeURIComponent(executionId)}/report`);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(typeof data.detail === "string" ? data.detail : "Could not download the validation report.");
      }
      const blob = await response.blob();
      const objectUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = `validation-report-${executionId}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setDocumentError(err.message.includes("Failed to fetch")
        ? "Cannot connect to FastAPI while downloading the report."
        : err.message);
    } finally {
      setReportLoading(false);
    }
  }

  async function runBenchmark() {
    setBenchmarkError("");
    setBenchmarkResult(null);
    setBenchmarkLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/benchmark`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          models: benchmarkModels,
          cases: BENCHMARK_CASES,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail || "Benchmark request failed.")
        );
      }

      setBenchmarkResult(data);
      await loadBenchmarkHistory();
    } catch (err) {
      setBenchmarkError(
        err.message.includes("Failed to fetch")
          ? "Cannot connect to FastAPI. Confirm the backend is running."
          : err.message
      );
    } finally {
      setBenchmarkLoading(false);
    }
  }

  const validation = result?.validation;

  // Support either summary/results or common alternate property names.
  const benchmarkSummaries =
    benchmarkResult?.summary ??
    benchmarkResult?.summaries ??
    [];

  const benchmarkResults =
    benchmarkResult?.results ??
    benchmarkResult?.case_results ??
    [];

  const qualityScores = executionHistory.map((item) => Number(item.validation?.quality_score)).filter((value) => Number.isFinite(value));
  const averageQualityScore = qualityScores.length ? qualityScores.reduce((sum, value) => sum + value, 0) / qualityScores.length : null;
  const latencyValues = executionHistory.map((item) => Number(item.total_latency_ms)).filter((value) => Number.isFinite(value) && value >= 0);
  const averageLatencyMs = latencyValues.length ? latencyValues.reduce((sum, value) => sum + value, 0) / latencyValues.length : null;

  const filteredExecutions = executionHistory.filter((item) => {
    const query = historySearch.trim().toLowerCase();
    const matchesQuery = !query || [item.execution_id, item.prompt, item.model, item.status]
      .some((value) => String(value || "").toLowerCase().includes(query));
    const matchesStatus = historyStatus === "all" || String(item.status || "").toLowerCase() === historyStatus;
    return matchesQuery && matchesStatus;
  });
  const filteredFailures = failureHistory.filter((item) => {
    const query = failureSearch.trim().toLowerCase();
    return !query || [item.execution_id, item.prompt, item.model, item.failure_type, item.recovery_strategy]
      .some((value) => String(value || "").toLowerCase().includes(query));
  });

  const navItems = [
    { id: "debugger", icon: "debugger", label: "AI Execution Debugger" },
    { id: "overview", icon: "overview", label: "Overview" },
    { id: "benchmarks", icon: "benchmarks", label: "LLM Evaluation & Benchmarks" },
    { id: "history", icon: "history", label: "Execution History" },
    { id: "failures", icon: "failures", label: "Needs Review" },
    { id: "disclosure", icon: "disclosure", label: "Model Insights" },
  ];

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">Q</div>
          <div>
            <h1>Response Quality Gate</h1>
            <p>AI execution, validation &amp; recovery</p>
          </div>
        </div>

        <span className="status-pill">LOCAL AI · OLLAMA</span>
      </header>

      <div className="app-layout">
        <aside className="sidebar" aria-label="Main navigation">
          <p className="sidebar-label">WORKSPACE</p>
          {navItems.slice(0, 3).map((item) => (
            <button key={item.id} type="button" className={`nav-item ${activePage === item.id ? "active" : ""}`} onClick={() => setActivePage(item.id)}>
              <span className="nav-icon"><AppIcon name={item.icon} size={17} /></span>{item.label}
            </button>
          ))}
          <p className="sidebar-label nav-section-label">OBSERVABILITY</p>
          {navItems.slice(3).map((item) => (
            <button key={item.id} type="button" className={`nav-item ${activePage === item.id ? "active" : ""}`} onClick={() => setActivePage(item.id)}>
              <span className="nav-icon"><AppIcon name={item.icon} size={17} /></span>{item.label}
            </button>
          ))}
          <div className="sidebar-note"><span className="status-dot" /> Local environment <small>Ollama · FastAPI</small></div>
        </aside>

        <div className="main-content" data-page={activePage}>
      <section className="hero" id="overview">
        <p className="eyebrow">AI ENGINEERING TOOLKIT <span className="hero-divider">/</span> LOCAL OBSERVABILITY</p>
        <h2>{activePage === "overview" ? "Trust every response." : navItems.find((item) => item.id === activePage)?.label || "AI Response Quality Gate"}</h2>
        <p>{activePage === "overview" ? "Monitor your local AI response validation workflow, compare models, and investigate saved execution results." : activePage === "debugger" ? "Configure a prompt, source evidence, JSON schema, retries, and fallback behavior. Inspect the full validation and recovery trace." : activePage === "benchmarks" ? "Evaluate local language models with the same test cases and inspect the metrics returned by your benchmark service." : activePage === "history" ? "Search, filter, and reopen persisted execution records from your SQLite-backed API." : activePage === "failures" ? "Investigate executions flagged for review, including their failure classification and recovery strategy." : "Review model usage, deployment context, evaluation limitations, and responsible-use notes."}</p>
      </section>

      <section className="overview-dashboard" aria-label="Live project overview">
        <div className="overview-heading"><div><span className="step-label">LIVE WORKSPACE</span><h2>Project overview</h2><p>Live counts from the execution records returned by your FastAPI backend.</p></div><button className="secondary-button" onClick={loadHistory} disabled={historyLoading}>{historyLoading ? "Refreshing…" : "↻ Refresh data"}</button></div>
        <div className="overview-stats">
          <button className="overview-stat" onClick={() => setActivePage("history")}><span>Executions loaded</span><strong>{executionHistory.length}</strong><small>Recent saved records · open history →</small></button>
          <button className="overview-stat" onClick={() => setActivePage("failures")}><span>Needs review</span><strong>{failureHistory.length}</strong><small>Investigate unresolved runs →</small></button>
          <button className="overview-stat" onClick={() => setActivePage("history")}><span>Average quality</span><strong>{averageQualityScore == null ? "—" : `${averageQualityScore.toFixed(1)}%`}</strong><small>{qualityScores.length ? `From ${qualityScores.length} loaded validations` : "No scored executions yet"}</small></button>
          <button className="overview-stat" onClick={() => setActivePage("history")}><span>Average latency</span><strong>{averageLatencyMs == null ? "—" : `${(averageLatencyMs / 1000).toFixed(2)} s`}</strong><small>{latencyValues.length ? `From ${latencyValues.length} loaded executions` : "No execution timings yet"}</small></button>
        </div>
        <div className="overview-lower"><div className="panel"><h3>Quick actions</h3><p>Run a structured prompt, compare local models, or investigate a saved execution.</p><div className="quick-actions"><button className="execute-button" onClick={() => { setResult(null); setSelectedExecutionId(null); setActivePage("debugger"); }}>＋ New execution</button><button className="secondary-button" onClick={() => setActivePage("benchmarks")}>Run model benchmark</button><button className="secondary-button" onClick={() => setActivePage("failures")}>Review failures</button></div></div><div className="panel"><h3>Latest activity</h3>{executionHistory.slice(0, 3).length ? executionHistory.slice(0, 3).map((item) => <button className="activity-row" key={item.execution_id} onClick={() => openExecution(item.execution_id)}><span className={`activity-dot ${item.status === "success" ? "success" : "warning"}`} /><span className="activity-copy"><strong>{shortenPrompt(item.prompt, 72)}</strong><small>{item.model || "Model unavailable"} · {item.created_at || "Date unavailable"}</small></span><span>→</span></button>) : <p className="empty-copy">{historyLoading ? "Loading live activity…" : "No execution records loaded. Run an execution or refresh the data."}</p>}</div></div>
      </section>

      <section className="workspace" id="debugger">
        {/* Prompt configuration */}
        <div className="panel input-panel">
          <div className="panel-heading">
            <div>
              <span className="step-label">01 / INPUT</span>
              <h2>Configure execution</h2>
            </div>
          </div>

          <label htmlFor="prompt">Prompt</label>
          <textarea
            id="prompt"
            rows="4"
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Ask the model to generate a structured response..."
          />

          <div className="source-field-heading">
            <label htmlFor="source">Source content (optional)</label>
          </div>
          <div className="source-composer">
            <textarea
              id="source"
              rows="3"
              value={sourceContent}
              onChange={(event) => setSourceContent(event.target.value)}
              placeholder="Paste reference text here, or attach a TXT/PDF file..."
            />
            <div className="source-composer-footer">
              <button
                type="button"
                className="source-attach-button"
                title="Attach a TXT or PDF document"
                aria-label="Attach a TXT or PDF document"
                onClick={() => document.getElementById("documentFile")?.click()}
              >
                <AppIcon name="plus" size={18} />
              </button>
              <span className="source-attachment-hint">{selectedFile ? selectedFile.name : "Optional reference evidence"}</span>
              {selectedFile && (
                <button
                  type="button"
                  className="source-remove-file"
                  onClick={() => {
                    setSelectedFile(null);
                    const fileInput = document.getElementById("documentFile");
                    if (fileInput) fileInput.value = "";
                    setDocumentError("");
                  }}
                  aria-label="Remove attached document"
                  title="Remove attached document"
                >
                  Remove
                </button>
              )}
            </div>
          </div>
          <input
            id="documentFile"
            className="source-file-input"
            type="file"
            accept=".txt,.pdf,text/plain,application/pdf"
            onChange={(event) => {
              const file = event.target.files?.[0] || null;
              setSelectedFile(file);
              setDocumentError("");
              if (file) setSourceContent("");
            }}
          />
          {selectedFile && <p className="selected-file source-selected-file"><AppIcon name="file" size={15} /> {selectedFile.name} · {(selectedFile.size / 1024).toFixed(1)} KB</p>}
          {documentError && <p className="error-message" role="alert">{documentError}</p>}

          <label htmlFor="schema">Expected JSON schema</label>
          <textarea
            id="schema"
            className="code-input"
            rows="8"
            value={schemaText}
            onChange={(event) => setSchemaText(event.target.value)}
            spellCheck="false"
          />

          <label htmlFor="model">Primary model</label>
          <select
            id="model"
            value={model}
            onChange={(event) => setModel(event.target.value)}
          >
            <option value="qwen3:4b">Qwen3 4B (local)</option>
            <option value="llama3.2:3b">Llama 3.2 3B (local)</option>
          </select>

          <label htmlFor="fallbackModel">Fallback model</label>
          <select
            id="fallbackModel"
            value={fallbackModel}
            onChange={(event) => setFallbackModel(event.target.value)}
          >
            <option value="llama3.2:3b">Llama 3.2 3B (local)</option>
            <option value="qwen3:4b">Qwen3 4B (local)</option>
            <option value="">No fallback</option>
          </select>

          <label htmlFor="maxRetries">Maximum retries</label>
          <select
            id="maxRetries"
            value={maxRetries}
            onChange={(event) => setMaxRetries(Number(event.target.value))}
          >
            <option value={0}>0 retries</option>
            <option value={1}>1 retry</option>
            <option value={2}>2 retries</option>
            <option value={3}>3 retries</option>
            <option value={4}>4 retries</option>
            <option value={5}>5 retries</option>
          </select>

          <button
            className="execute-button"
            onClick={selectedFile ? executeDocument : executePrompt}
            disabled={loading || documentLoading}
          >
            {loading || documentLoading ? "Executing model…" : "Execute & Validate"}
          </button>

          {error && <p className="error-message">{error}</p>}

          <p className="hint">
            Runs against your local FastAPI backend. Retry limit: {maxRetries}.
          </p>
        </div>

        {/* Single execution results */}
        <div className="results-column">
          <div className="panel result-panel">
            <div className="panel-heading">
              <div>
                <span className="step-label">02 / VALIDATION</span>
                <h2>{selectedExecutionId ? "Execution detail" : "Quality overview"}</h2>
                {selectedExecutionId && <p className="hint">Loaded saved execution: {selectedExecutionId}</p>}
              </div>

              {result && (
                <span
                  className={`status-pill ${
                    result.status === "success" ? "good" : "review"
                  }`}
                >
                  {result.status === "success" ? "PASSED" : "NEEDS REVIEW"}
                </span>
              )}
            </div>

            <div className="score-grid">
              <ScoreCard
                label="Quality"
                score={validation?.quality_score}
              />
              <ScoreCard
                label="Grounding"
                score={validation?.grounding_available === false ? null : validation?.grounding_score}
              />
              <ScoreCard
                label="Completeness"
                score={validation?.completeness_score}
              />
            </div>

            {result && validation?.grounding_available === false && (
              <div className="validation-notice warning-notice" role="status">
                <strong>Grounding not verified</strong>
                <p>No source content was provided, so the validator cannot verify the response against reference evidence. This does not automatically mean the response is false.</p>
              </div>
            )}

            {!!validation?.validation_warnings?.length && (
              <div className="validation-notice warning-notice" role="status">
                <strong>Validation warnings</strong>
                <ul>
                  {validation.validation_warnings.map((warning, index) => (
                    <li key={`${index}-${warning}`}>{warning}</li>
                  ))}
                </ul>
              </div>
            )}

            {!result && (
              <div className="empty-state">
                <span className="empty-icon">◎</span>
                <h3>Ready for analysis</h3>
                <p>Execute a prompt to see validation results here.</p>
              </div>
            )}

            {result && (
              <>
                <div className="detail-grid">
                  <div>
                    <span>Failure type</span>
                    <strong>{result.failure_type || "Unknown"}</strong>
                  </div>
                  <div>
                    <span>Recovery strategy</span>
                    <strong>{result.recovery_strategy || "—"}</strong>
                  </div>
                  <div>
                    <span>Retries</span>
                    <strong>{result.retry_count ?? 0}</strong>
                  </div>
                  <div>
                    <span>Total latency</span>
                    <strong>{formatLatency(result.total_latency_ms)}</strong>
                  </div>
                  <div>
                    <span>Model used</span>
                    <strong>{result.model_used || model}</strong>
                  </div>
                  <div>
                    <span>Fallback used</span>
                    <strong>
                      {result.fallback_model_used ? "Yes" : "No"}
                    </strong>
                  </div>
                </div>

                <h3 className="section-title">Original response</h3>
                <pre>{formatResponse(result.original_response)}</pre>

                <h3 className="section-title">Initial validation</h3>
                {result.initial_validation ? (
                  <>
                    <div className="score-grid">
                      <ScoreCard
                        label="Initial quality"
                        score={result.initial_validation.quality_score}
                      />
                      <ScoreCard
                        label="Initial grounding"
                        score={result.initial_validation.grounding_score}
                      />
                      <ScoreCard
                        label="Initial completeness"
                        score={result.initial_validation.completeness_score}
                      />
                    </div>
                    <p className="hint">
                      These scores describe the first model response, before
                      retries or fallback recovery.
                    </p>
                  </>
                ) : (
                  <p>Initial validation details were not returned.</p>
                )}

                <h3 className="section-title">Final recovered response</h3>
                <pre>{formatResponse(result.final_response)}</pre>

                <h3 className="section-title">Evidence-linked validation</h3>

                {validation?.evidence_findings?.length ? (
                  <div className="evidence-list">
                    {validation.evidence_findings.map((finding, index) => (
                      <div className="evidence-card" key={index}>
                        <div className="evidence-card-header">
                          <strong>{finding.claim}</strong>
                          <span
                            className={`evidence-badge ${finding.classification}`}
                          >
                            {finding.classification}
                          </span>
                        </div>

                        <p>
                          <strong>Source evidence:</strong>{" "}
                          {finding.evidence ||
                            "No matching source evidence found."}
                        </p>

                        <p>
                          <strong>Explanation:</strong>{" "}
                          {finding.explanation}
                        </p>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p>
                    No evidence findings available. Provide source content
                    to enable evidence-linked checks.
                  </p>
                )}

                <h3 className="section-title">Contradictions</h3>
                {validation?.contradictions?.length ? (
                  <ul>
                    {validation.contradictions.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No contradictions reported by the current validator.</p>
                )}

                <h3 className="section-title">Hallucinations / issues</h3>
                {validation?.hallucinations?.length ? (
                  <ul>
                    {validation.hallucinations.map((item, index) => (
                      <li key={index}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No issues reported by the current validator.</p>
                )}

                <h3 className="section-title">Recommended actions</h3>
                {validation?.recommended_actions?.length ? (
                  <ul>
                    {validation.recommended_actions.map((action, index) => (
                      <li key={index}>{action}</li>
                    ))}
                  </ul>
                ) : (
                  <p>No actions recommended.</p>
                )}

                <h3 className="section-title">Execution trace</h3>
                {result.execution_trace?.length ? (
                  <ol className="trace-list">
                    {result.execution_trace.map((entry, index) => (
                      <li key={index}>{entry}</li>
                    ))}
                  </ol>
                ) : (
                  <p>No execution trace returned.</p>
                )}

                <div className="execution-report-actions">
                  <p className="execution-id">Execution ID: {result.execution_id || "Not returned"}</p>
                  {result.execution_id && (
                    <button type="button" className="secondary-button" onClick={() => downloadValidationReport(result.execution_id)} disabled={reportLoading}>
                      <AppIcon name="download" size={16} /> {reportLoading ? "Preparing report…" : "Download validation report"}
                    </button>
                  )}
                </div>
                {documentError && <p className="error-message" role="alert">{documentError}</p>}
              </>
            )}
          </div>
        </div>
      </section>

      {/* Benchmark comparison */}
      <section className="panel benchmark-panel" id="benchmarks">
        <div className="panel-heading">
          <div>
            <span className="step-label">03 / EVALUATION</span>
            <h2>Model Comparison</h2>
          </div>

          <button
            className="execute-button"
            onClick={runBenchmark}
            disabled={benchmarkLoading || benchmarkModels.length !== 2}
          >
            {benchmarkLoading ? "Benchmarking…" : `Run ${benchmarkModels.length} model${benchmarkModels.length === 1 ? "" : "s"}`}
          </button>
        </div>

        <p>
          Run the same fixed test cases against selected local models. Results below are returned by the benchmark API; no comparison values are fabricated.
        </p>
        <div className="benchmark-controls">
          <span className="control-label">Models included in this run</span>
          {[{id:"qwen3:4b", label:"Qwen3 4B"}, {id:"llama3.2:3b", label:"Llama 3.2 3B"}].map((item) => (
            <label className="model-check" key={item.id}><input type="checkbox" checked={benchmarkModels.includes(item.id)} onChange={(event) => setBenchmarkModels((current) => event.target.checked ? [...current, item.id] : current.filter((value) => value !== item.id))} />{item.label}<span>Local · Ollama</span></label>
          ))}
          <span className="hint">Test suite: {BENCHMARK_CASES.length} fixed source-grounded JSON cases · same schemas per model. Select both models for a valid comparison.</span>
        </div>

        {benchmarkError && (
          <p className="error-message">{benchmarkError}</p>
        )}

        {!benchmarkResult && !benchmarkLoading && (
          <div className="empty-state">
            <h3>Ready to compare models</h3>
            <p>
              Run the benchmark to measure quality, grounding, latency,
              JSON reliability, schema reliability, and validation pass rate.
            </p>
          </div>
        )}

        {benchmarkLoading && (
          <p>
            Running test cases against the selected local models. This may take a few minutes.
          </p>
        )}

        {benchmarkRunHistory.length > 0 && (
          <div className="saved-benchmarks"><div><strong>Saved benchmark runs</strong><span>Persisted in SQLite · latest {benchmarkRunHistory.length} runs</span><button type="button" className="secondary-button" onClick={loadBenchmarkHistory}>Refresh saved runs</button></div>{benchmarkRunHistory.map((run, index) => <button key={run.run_id || `saved-run-${index}`} className={`saved-run-button ${benchmarkResult?.run_id === run.run_id ? "selected" : ""}`} onClick={() => openBenchmark(run.run_id)}><span>{run.run_id || `Benchmark ${benchmarkRunHistory.length - index}`}</span><small>{(run.summaries || []).map((item) => item.model).filter(Boolean).join(" vs ") || (run.models || []).join(" vs ") || "Model comparison"} · {run.created_at || "Saved run"}</small></button>)}</div>
        )}

        {benchmarkResult && (
          <>
            <p>
              <strong>Benchmark run ID:</strong>{" "}
              {benchmarkResult.run_id || "Not returned"}
            </p>

            {benchmarkSummaries.length > 0 ? (
              <div className="benchmark-grid">
                {benchmarkSummaries.map((item) => (
                  <div className="score-card benchmark-model" key={item.model}>
                    <h3>{item.model}</h3>

                    <div className="benchmark-metric">
                      <span>Average quality</span>
                      <strong>
                        {formatPercent(item.average_quality_score)}
                      </strong>
                    </div>

                    <div className="benchmark-metric">
                      <span>Grounding</span>
                      <strong>
                        {formatPercent(item.average_grounding_score)}
                      </strong>
                    </div>

                    <div className="benchmark-metric">
                      <span>Completeness</span>
                      <strong>
                        {formatPercent(item.average_completeness_score)}
                      </strong>
                    </div>

                    <div className="benchmark-metric">
                      <span>Average latency</span>
                      <strong>
                        {formatLatency(item.average_latency_ms)}
                      </strong>
                    </div>

                    <div className="benchmark-metric">
                      <span>JSON reliability</span>
                      <strong>
                        {formatPercent(item.json_reliability_percent)}
                      </strong>
                    </div>

                    <div className="benchmark-metric">
                      <span>Schema reliability</span>
                      <strong>
                        {formatPercent(item.schema_reliability_percent)}
                      </strong>
                    </div>

                    <div className="benchmark-metric">
                      <span>Validation pass rate</span>
                      <strong>
                        {formatPercent(item.validation_pass_rate_percent)}
                      </strong>
                    </div>

                    <p className="hint">
                      {item.successful_runs ?? "—"} successful runs out of{" "}
                      {item.cases_run ?? "—"} cases.
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p>
                No model summaries were returned. Check the response in
                FastAPI Swagger UI.
              </p>
            )}

            <h3 className="section-title">Model comparison interpretation</h3>
            <p className="hint">Recommendations below are decision support based on this benchmark run, not a guarantee of production readiness. Cost is local compute cost, not a verified monetary price estimate.</p>
            <div className="model-comparison-notes">
              {benchmarkSummaries.map((item) => {
                const schemaReliability = Number(item.schema_reliability_percent);
                const quality = Number(item.average_quality_score);
                const useCase = Number.isFinite(schemaReliability) && schemaReliability >= 95
                  ? "Promising for schema-constrained local prototyping on this test suite; validate on representative prompts before adoption."
                  : "Better treated as an exploratory assistant for this test suite; use explicit schema checks and recovery before consuming structured output.";
                return (
                  <article className="panel model-comparison-note" key={`interpretation-${item.model}`}>
                    <h4>{item.model}</h4>
                    <p><strong>Observed limitation:</strong> {observedLimitation(item.model, benchmarkResults)}</p>
                    <p><strong>Recommended use case:</strong> {useCase}</p>
                    <p><strong>Cost vs performance:</strong> Local Ollama inference avoids hosted per-token API fees, but response time and memory use depend on the user's hardware. Compare this model's measured latency with its scores above.</p>
                    <p><strong>Production recommendation:</strong> Do not approve production use from this small POC benchmark alone. Run a representative evaluation set, add semantic/factual verification, and define acceptance thresholds.</p>
                  </article>
                );
              })}
            </div>

            <h3 className="section-title">Individual test results</h3>

            {benchmarkResults.length > 0 ? (
              benchmarkResults.map((item, index) => (
                <div
                  className="evidence-card benchmark-case"
                  key={`${item.model || "model"}-${index}`}
                >
                  <div className="evidence-card-header">
                    <strong>
                      {item.model || "Model"} — Case {index + 1}
                    </strong>

                    <StatusBadge
                      passed={item.validation_passed === true}
                      label={
                        item.validation_passed === true
                          ? "Validation passed"
                          : "Needs review"
                      }
                    />
                  </div>

                  <p>
                    <strong>JSON valid:</strong>{" "}
                    {item.json_valid == null
                      ? "Not measured"
                      : item.json_valid
                        ? "Yes"
                        : "No"}
                  </p>

                  <p>
                    <strong>Schema valid:</strong>{" "}
                    {item.schema_valid == null
                      ? "Not measured"
                      : item.schema_valid
                        ? "Yes"
                        : "No"}
                  </p>

                  <p>
                    <strong>Latency:</strong>{" "}
                    {formatLatency(item.latency_ms)}
                  </p>

                  <p>
                    <strong>Failure type:</strong>{" "}
                    {item.failure_type || "—"}
                  </p>

                  <p><strong>Model response:</strong></p>
                  <pre>{formatResponse(item.response)}</pre>

                  {!!item.contradictions?.length && (
                    <>
                      <p><strong>Contradictions:</strong></p>
                      <ul>
                        {item.contradictions.map((finding, findingIndex) => (
                          <li key={findingIndex}>{finding}</li>
                        ))}
                      </ul>
                    </>
                  )}

                  {!!item.hallucinations?.length && (
                    <>
                      <p><strong>Unsupported claims / issues:</strong></p>
                      <ul>
                        {item.hallucinations.map((finding, findingIndex) => (
                          <li key={findingIndex}>{finding}</li>
                        ))}
                      </ul>
                    </>
                  )}

                  {!!item.evidence_findings?.length && (
                    <>
                      <p><strong>Evidence findings:</strong></p>
                      {item.evidence_findings.map((finding, findingIndex) => (
                        <div key={findingIndex}>
                          <p>
                            <strong>{finding.claim}</strong>{" "}
                            — {finding.classification}
                          </p>
                          <p>
                            <strong>Source:</strong>{" "}
                            {finding.evidence || "No matching evidence"}
                          </p>
                          <p>
                            <strong>Explanation:</strong>{" "}
                            {finding.explanation}
                          </p>
                        </div>
                      ))}
                    </>
                  )}

                  {!!item.recommended_actions?.length && (
                    <>
                      <p><strong>Recommended actions:</strong></p>
                      <ul>
                        {item.recommended_actions.map((action, actionIndex) => (
                          <li key={actionIndex}>{action}</li>
                        ))}
                      </ul>
                    </>
                  )}
                </div>
              ))
            ) : (
              <p>No individual benchmark results were returned.</p>
            )}

            <p className="hint">
              Interpretation note: JSON validity means the response can be
              parsed as JSON. Schema validity means it matches the requested
              structure. Neither guarantees factual accuracy. Quality and
              grounding scores depend on the current validator and should
              be interpreted as automated estimates, not proof of truth.
            </p>
          </>
        )}
      </section>

      {/* Persistent execution and failure history */}
      <section className="panel benchmark-panel" id="history">
        <div className="panel-heading">
          <div>
            <span className="step-label">04 / HISTORY</span>
            <h2>{activePage === "failures" ? "Failed Executions / Needs Review" : "Execution History"}</h2>
          </div>
          <button
            className="execute-button"
            onClick={loadHistory}
            disabled={historyLoading}
          >
            {historyLoading ? "Refreshing..." : "↻ Refresh History"}
          </button>
        </div>

        <p>
          Search saved executions by prompt, model, status, or execution ID. Select a row to open the full execution detail in the debugger.
        </p>
        <div id="execution-history-content">
        <div className="table-toolbar"><input aria-label="Search execution history" value={historySearch} onChange={(event) => setHistorySearch(event.target.value)} placeholder="Search prompt, model, status, execution ID…" /><select aria-label="Filter execution status" value={historyStatus} onChange={(event) => setHistoryStatus(event.target.value)}><option value="all">All statuses</option><option value="success">Success</option><option value="failed">Failed</option><option value="failure">Failure</option><option value="error">Error</option><option value="needs_review">Needs review</option></select><span>{filteredExecutions.length} results</span></div>

        {historyError && <p className="error-message">{historyError}</p>}

        {filteredExecutions.length > 0 ? (
          <div className="evidence-list">
            {filteredExecutions.slice(0, visibleExecutions).map((item) => (
              <div className="evidence-card history-card" key={item.execution_id}>
                <div className="evidence-card-header">
                  <strong>{item.status || "Unknown status"}</strong>
                  <StatusBadge
                    passed={item.status === "success"}
                    label={item.status === "success" ? "Success" : "Needs review"}
                  />
                </div>
                <p className="history-prompt" title={item.prompt || "Prompt not available"}>
                  {shortenPrompt(item.prompt)}
                </p>
                <div className="history-meta">
                  <span><b>Model</b>{item.model || "—"}</span>
                  <span><b>Retries</b>{item.retry_count ?? 0}</span>
                  <span><b>Latency</b>{formatLatency(item.total_latency_ms)}</span>
                  <span><b>Date</b>{item.created_at || "—"}</span>
                </div>
                <button
                  className="execute-button"
                  onClick={() => openExecution(item.execution_id)}
                >
                  View execution details
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p>{historyLoading ? "Loading executions..." : "No execution history returned yet."}</p>
        )}
        {filteredExecutions.length > visibleExecutions && (
          <button className="execute-button history-more-button" onClick={() => setVisibleExecutions((count) => count + 5)}>
            Load more executions ({filteredExecutions.length - visibleExecutions} remaining)
          </button>
        )}

        </div>
        <div id="failure-content">
        <h3 className="section-title" id="failures">Failed Executions / Needs Review</h3>
        <p className="hint">
          These are executions the validator did not accept. A failure record is not automatically proof that the model response is factually false.
        </p>
        <div className="table-toolbar"><input aria-label="Search failed executions" value={failureSearch} onChange={(event) => setFailureSearch(event.target.value)} placeholder="Search failure type, prompt, model, recovery…" /><span>{filteredFailures.length} records to review</span></div>

        {filteredFailures.length > 0 ? (
          <div className="evidence-list">
            {filteredFailures.slice(0, visibleFailures).map((item) => (
              <div className="evidence-card history-card" key={item.execution_id}>
                <div className="evidence-card-header">
                  <strong>{item.failure_type || "Unclassified failure"}</strong>
                  <StatusBadge passed={false} label="Needs review" />
                </div>
                <p className="history-prompt" title={item.prompt || "Prompt not available"}>
                  {shortenPrompt(item.prompt)}
                </p>
                <div className="history-meta">
                  <span><b>Model</b>{item.model || "—"}</span>
                  <span><b>Retries</b>{item.retry_count ?? 0}</span>
                  <span><b>Latency</b>{formatLatency(item.total_latency_ms)}</span>
                  <span><b>Recovery</b>{item.recovery_strategy || "—"}</span>
                </div>
                <button
                  className="execute-button"
                  onClick={() => openExecution(item.execution_id)}
                >
                  Inspect failed execution
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p>{historyLoading ? "Loading failures..." : "No executions currently need review."}</p>
        )}
        {filteredFailures.length > visibleFailures && (
          <button className="execute-button history-more-button" onClick={() => setVisibleFailures((count) => count + 5)}>
            Load more failed executions ({filteredFailures.length - visibleFailures} remaining)
          </button>
        )}
        </div>
      </section>

      {/* Model disclosure */}
      <section className="panel disclosure-panel" id="disclosure">
        <div className="panel-heading">
          <div>
            <span className="step-label">05 / TRANSPARENCY</span>
            <h2>AI Model Disclosure</h2>
          </div>
        </div>

        <div className="detail-grid">
          <div><span>Models evaluated</span><strong>Qwen3 4B · Llama 3.2 3B</strong></div>
          <div><span>LLM / SLM classification</span><strong>Small language models (SLMs; compact LLMs)</strong></div>
          <div><span>Platform used</span><strong>Ollama</strong></div>
          <div><span>Deployment type</span><strong>Local inference on the development machine</strong></div>
          <div><span>Use case</span><strong>Source-grounded structured generation, JSON/schema validation, and local model comparison</strong></div>
          <div><span>Reason for selection</span><strong>Local, low-cost, privacy-friendly prototyping with two model sizes suitable for side-by-side evaluation</strong></div>
          <div><span>Cost vs performance</span><strong>No hosted inference fee for local runs; latency and capacity depend on available hardware</strong></div>
          <div><span>Production recommendation</span><strong>Use representative benchmarks, stronger semantic verification, monitoring, and human review for high-impact decisions</strong></div>
        </div>
        <div className="overview-lower model-disclosure-observations">
          <div className="panel">
            <h3>Qwen3 4B — observed limitation</h3>
            <p>{observedLimitation("qwen3:4b", benchmarkResults)}</p>
          </div>
          <div className="panel">
            <h3>Llama 3.2 3B — observed limitation</h3>
            <p>{observedLimitation("llama3.2:3b", benchmarkResults)}</p>
          </div>
        </div>
        <p>
          The models generate candidate responses. The application then
          evaluates response structure, evidence matching, and selected
          quality indicators. Model outputs are not guaranteed to be true.
          The application is a local prototype, not a production safety
          guarantee.
        </p>
      </section>

        <footer>
          AI Response Quality Gate <span>·</span> Local model evaluation
        </footer>
        </div>
      </div>
    </main>
  );
}

export default App;
