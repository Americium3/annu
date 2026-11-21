import { useEffect, useState } from "react";

function getInitialMatch(query: string) {
  if (typeof window === "undefined") return false;
  return window.matchMedia(query).matches;
}

export function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => getInitialMatch(query));

  useEffect(() => {
    const mediaQuery = window.matchMedia(query);
    function updateMatch(event: MediaQueryListEvent) {
      setMatches(event.matches);
    }

    setMatches(mediaQuery.matches);
    mediaQuery.addEventListener("change", updateMatch);
    return () => mediaQuery.removeEventListener("change", updateMatch);
  }, [query]);

  return matches;
}
