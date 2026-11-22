import { useEffect } from "react";
import { auth, useSession } from "../lib/auth";
import { useProfile } from "../lib/profile";

/** While signed in, copy preference changes to the account. Renders nothing. */
export function AccountSync() {
  const session = useSession();
  const profile = useProfile();
  useEffect(() => {
    if (session) void auth.saveProfile(session, profile);
  }, [profile, session]);
  return null;
}
