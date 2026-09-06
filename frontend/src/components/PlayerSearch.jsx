import { useState } from "react";
import { REGIONS } from "../utils.js";

// `nameRef` (optional) exposes the name input so the landing's "Track your
// Riot ID" CTA can focus it.
export default function PlayerSearch({ initial, onSearch, nameRef }) {
  const [name, setName] = useState(initial ? initial.name : "");
  const [tag, setTag] = useState(initial ? initial.tag : "");
  const [region, setRegion] = useState(initial ? initial.region : "na");

  function handleSubmit(e) {
    e.preventDefault();
    let n = name.trim();
    let t = tag.trim().replace(/^#/, "");
    // Allow pasting a full "Name#TAG" into the name field
    if (n.includes("#")) {
      const [head, ...rest] = n.split("#");
      n = head.trim();
      if (!t) t = rest.join("#").trim();
    }
    if (!n || !t) return;
    setName(n);
    setTag(t);
    onSearch({ name: n, tag: t, region });
  }

  return (
    <form className="search" onSubmit={handleSubmit}>
      <input
        ref={nameRef}
        className="search-name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Player name"
        aria-label="Player name"
        autoComplete="off"
        spellCheck="false"
      />
      <div className="tag-field">
        <span aria-hidden="true">#</span>
        <input
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          placeholder="TAG"
          aria-label="Tagline"
          autoComplete="off"
          spellCheck="false"
        />
      </div>
      <select
        value={region}
        onChange={(e) => setRegion(e.target.value)}
        aria-label="Region"
      >
        {REGIONS.map((r) => (
          <option key={r} value={r}>
            {r.toUpperCase()}
          </option>
        ))}
      </select>
      <button type="submit" className="btn accent">
        Track
      </button>
    </form>
  );
}
