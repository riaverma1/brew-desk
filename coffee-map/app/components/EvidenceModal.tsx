"use client";

type EvidenceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  attributeName: string;
  evidence: string[];
  sources: string[];
};

export default function EvidenceModal({
  isOpen,
  onClose,
  attributeName,
  evidence,
  sources,
}: EvidenceModalProps) {
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: "white",
          borderRadius: 8,
          padding: 24,
          maxWidth: 600,
          maxHeight: "80vh",
          overflowY: "auto",
          boxShadow: "0 4px 16px rgba(0,0,0,0.2)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600 }}>
            Evidence for {attributeName.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
          </h2>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: 24,
              cursor: "pointer",
              padding: 0,
              width: 30,
              height: 30,
            }}
          >
            ×
          </button>
        </div>

        {sources.length > 0 && (
          <div style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Sources:</h3>
            <ul style={{ margin: 0, paddingLeft: 20, fontSize: 12, color: "#666" }}>
              {sources.map((source, idx) => (
                <li key={idx}>{source}</li>
              ))}
            </ul>
          </div>
        )}

        {evidence.length > 0 ? (
          <div>
            <h3 style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>Evidence:</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {evidence.map((item, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: 12,
                    background: "#f9f9f9",
                    borderRadius: 4,
                    fontSize: 13,
                    lineHeight: 1.5,
                    borderLeft: "3px solid #1976d2",
                  }}
                >
                  {item}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p style={{ color: "#666", fontSize: 13 }}>No evidence available for this attribute.</p>
        )}
      </div>
    </div>
  );
}

