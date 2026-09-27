import { useEffect, useState } from "react";

export function useCircularsData() {
  const [data, setData] = useState({ generated_at: null, circulars: [] });
  const [status, setStatus] = useState("loading"); // loading | ready | error

  useEffect(() => {
    let cancelled = false;
    fetch("/data/circulars.json", { cache: "no-store" })
      .then((res) => {
        if (!res.ok) throw new Error(`fetch failed: ${res.status}`);
        return res.json();
      })
      .then((json) => {
        if (!cancelled) {
          setData(json);
          setStatus("ready");
        }
      })
      .catch((err) => {
        console.error(err);
        if (!cancelled) setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { data, status };
}
