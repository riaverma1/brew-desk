"use client";

type DerivedAttribute = {
  value: string | string[];
  confidence: number;
  evidence: string[];
  sources: string[];
};

type Place = {
  id: string;
  name: string;
  address?: string;
  rating?: number;
  userRatingCount?: number;
  restroom?: boolean;
  servesCoffee?: boolean;
  outdoorSeating?: boolean;
  derived?: {
    has_wifi?: DerivedAttribute;
    has_outlets?: DerivedAttribute;
    is_laptop_friendly?: DerivedAttribute;
    noise_level?: DerivedAttribute;
    seating_availability?: DerivedAttribute;
    seating_comfort?: DerivedAttribute;
    open_after_7pm?: DerivedAttribute;
    notable_positives?: DerivedAttribute;
    common_complaints?: DerivedAttribute;
  };
  enriched_flag: boolean;
  enriching?: boolean;
};

type PlaceTooltipProps = {
  place: Place;
  onShowEvidence: (attributeName: string, evidence: string[], sources: string[]) => void;
};

export default function PlaceTooltip({ place, onShowEvidence }: PlaceTooltipProps) {
  const formatAttributeName = (name: string) => {
    return name.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase());
  };

  const formatAttributeValue = (attr: DerivedAttribute) => {
    if (Array.isArray(attr.value)) {
      return attr.value.join(", ");
    }
    return attr.value;
  };

  const renderAttribute = (key: string, attr: DerivedAttribute | undefined) => {
    if (!attr || attr.value === "unknown" || (Array.isArray(attr.value) && attr.value.length === 0)) {
      return null;
    }

    return (
      <div key={key} style={{ marginBottom: 8, fontSize: 12 }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>
          {formatAttributeName(key)}: {formatAttributeValue(attr)}
          {attr.confidence > 0 && (
            <span style={{ color: "#666", fontWeight: 400, marginLeft: 4 }}>
              ({Math.round(attr.confidence * 100)}% confidence)
            </span>
          )}
        </div>
        {attr.evidence && attr.evidence.length > 0 && (
          <button
            onClick={() => onShowEvidence(key, attr.evidence, attr.sources || [])}
            style={{
              background: "#1976d2",
              color: "white",
              border: "none",
              padding: "4px 8px",
              borderRadius: 4,
              cursor: "pointer",
              fontSize: 11,
            }}
          >
            Show Evidence
          </button>
        )}
      </div>
    );
  };

  const renderBooleanAttribute = (label: string, value: boolean | undefined) => {
    if (value === undefined || value === null) return null;
    return (
      <div style={{ marginBottom: 4, fontSize: 12 }}>
        <strong>{label}:</strong> {value ? "Yes" : "No"}
      </div>
    );
  };

  return (
    <div style={{ maxWidth: 300, padding: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 14, marginBottom: 6 }}>{place.name}</div>
      {place.address && (
        <div style={{ fontSize: 12, marginBottom: 6, color: "#666" }}>{place.address}</div>
      )}
      {place.rating && (
        <div style={{ fontSize: 12, marginBottom: 6 }}>
          ⭐ {place.rating} ({place.userRatingCount || 0} reviews)
        </div>
      )}

      {/* Place Detail Attributes */}
      <div style={{ marginTop: 8, marginBottom: 8, paddingTop: 8, borderTop: "1px solid #eee" }}>
        <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, color: "#666" }}>Amenities</div>
        {renderBooleanAttribute("Restroom", place.restroom)}
        {renderBooleanAttribute("Serves Coffee", place.servesCoffee)}
        {renderBooleanAttribute("Outdoor Seating", place.outdoorSeating)}
      </div>

      {/* Derived Attributes */}
      {place.derived && (
        <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #eee" }}>
          <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4, color: "#666" }}>
            Work From Home Attributes
          </div>
          {renderAttribute("has_wifi", place.derived.has_wifi)}
          {renderAttribute("has_outlets", place.derived.has_outlets)}
          {renderAttribute("is_laptop_friendly", place.derived.is_laptop_friendly)}
          {renderAttribute("noise_level", place.derived.noise_level)}
          {renderAttribute("seating_availability", place.derived.seating_availability)}
          {renderAttribute("seating_comfort", place.derived.seating_comfort)}
          {renderAttribute("open_after_7pm", place.derived.open_after_7pm)}
          {renderAttribute("notable_positives", place.derived.notable_positives)}
          {renderAttribute("common_complaints", place.derived.common_complaints)}
        </div>
      )}

      {/* Enrichment Status */}
      {place.enriching && (
        <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid #eee", fontSize: 11, color: "#666" }}>
          <span style={{ display: "inline-block", width: 12, height: 12, borderRadius: "50%", background: "#ffa726", marginRight: 6 }} />
          Enrichment in progress...
        </div>
      )}
    </div>
  );
}

