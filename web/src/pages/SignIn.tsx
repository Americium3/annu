import { ArrowLeft, ArrowRight, LoaderCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Header } from "../components/Header";
import { RaahiSays } from "../components/Raahi";
import { useI18n } from "../i18n";
import { auth, AuthError, completeSignIn, DEMO_CODE, formatPhone, safeReturnTo, useSession } from "../lib/auth";
import { withTransition } from "../lib/motion";
import { isValidMobile } from "../lib/profile";

/**
 * Mobile number + one-time code. Two short screens, numeric keyboards, the
 * code field set up for SMS autofill, and a visible way out ("Continue without
 * signing in") because nothing on CarePath needs an account.
 */
export function SignIn() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const returnTo = safeReturnTo(params.get("return_to"));
  const session = useSession();

  const [stage, setStage] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resendIn, setResendIn] = useState(0);
  const codeRef = useRef<HTMLInputElement>(null);
  const phoneRef = useRef<HTMLInputElement>(null);

  const digits = phone.replace(/\D/g, "").replace(/^(91|0)(?=\d{10}$)/, "");

  // Already signed in (e.g. Back after signing in): go where they were headed.
  useEffect(() => {
    if (session && !busy) navigate(returnTo, { replace: true });
  }, [busy, navigate, returnTo, session]);

  useEffect(() => {
    if (resendIn <= 0) return;
    const timer = window.setTimeout(() => setResendIn((seconds) => seconds - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [resendIn]);

  useEffect(() => {
    (stage === "code" ? codeRef : phoneRef).current?.focus();
  }, [stage]);

  function describe(failure: unknown) {
    if (failure instanceof AuthError) {
      if (failure.code === "invalid_phone") return t.siPhoneError;
      if (failure.code === "wrong_code") return t.siWrongCode;
    }
    return t.siNetwork;
  }

  async function sendCode() {
    setError(null);
    if (!isValidMobile(digits)) {
      setError(t.siPhoneError);
      return;
    }
    setBusy(true);
    try {
      const { resendAfterSeconds } = await auth.requestOtp(digits);
      setResendIn(resendAfterSeconds);
      setCode("");
      withTransition(() => setStage("code"), "step");
    } catch (failure) {
      setError(describe(failure));
    } finally {
      setBusy(false);
    }
  }

  async function verify(value = code) {
    if (value.length !== 6 || busy) return;
    setError(null);
    setBusy(true);
    try {
      const { session: next, savedProfile } = await auth.verifyOtp(digits, value);
      await completeSignIn(next, savedProfile);
      navigate(returnTo, { replace: true });
    } catch (failure) {
      setError(describe(failure));
      setCode("");
      codeRef.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-shell">
      <Header />
      <main className="flow">
        <div className="flow-inner flow-narrow">
          <section className="flow-card" aria-live="polite">
            {stage === "phone" ? (
              <form
                noValidate
                onSubmit={(event) => {
                  event.preventDefault();
                  void sendCode();
                }}
              >
                <RaahiSays size={64}>
                  <h1>{t.siTitle}</h1>
                </RaahiSays>
                <p className="flow-hint">{t.siWhy}</p>
                <label className="field-label" htmlFor="si-phone">
                  {t.siPhoneLabel}
                </label>
                <div className="text-field phone-field">
                  <span aria-hidden="true">+91</span>
                  <input
                    id="si-phone"
                    ref={phoneRef}
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    type="tel"
                    inputMode="numeric"
                    autoComplete="tel-national"
                    enterKeyHint="send"
                    maxLength={14}
                    placeholder="98765 43210"
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? "si-error" : undefined}
                  />
                </div>
                {error && (
                  <p className="field-message" id="si-error" role="alert">
                    {error}
                  </p>
                )}
                <div className="flow-actions">
                  <button type="submit" className="primary-button flow-primary" disabled={busy}>
                    {busy ? <LoaderCircle className="spin" size={18} /> : null}
                    {busy ? t.siSending : t.siSendCode}
                    {!busy && <ArrowRight size={18} aria-hidden="true" />}
                  </button>
                </div>
              </form>
            ) : (
              <form
                noValidate
                onSubmit={(event) => {
                  event.preventDefault();
                  void verify();
                }}
              >
                <button
                  type="button"
                  className="back-button"
                  onClick={() => {
                    withTransition(() => setStage("phone"), "step");
                    setError(null);
                  }}
                >
                  <ArrowLeft size={18} aria-hidden="true" />
                  {t.siChangeNumber}
                </button>
                <h1 className="flow-title">{t.siCodeTitle}</h1>
                <p className="flow-hint">{t.siCodeSent(formatPhone(digits))}</p>
                <label className="field-label" htmlFor="si-code">
                  {t.siCodeLabel}
                </label>
                {/* Six boxes for the eye; one real input underneath for SMS autofill,
                    paste and screen readers. */}
                <div className={`code-boxes ${error ? "has-error" : ""}`}>
                  {Array.from({ length: 6 }, (_, position) => (
                    <span
                      key={position}
                      aria-hidden="true"
                      className={`code-box ${code[position] ? "is-filled" : ""} ${
                        position === Math.min(code.length, 5) ? "is-next" : ""
                      }`}
                    >
                      {code[position] ?? ""}
                    </span>
                  ))}
                  <input
                    id="si-code"
                    ref={codeRef}
                    value={code}
                    onChange={(event) => {
                      const value = event.target.value.replace(/\D/g, "").slice(0, 6);
                      setCode(value);
                      // SMS autofill and paste arrive all at once: sign in straight away.
                      if (value.length === 6) void verify(value);
                    }}
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    enterKeyHint="done"
                    maxLength={6}
                    aria-invalid={Boolean(error)}
                    aria-describedby={error ? "si-error" : "si-demo"}
                  />
                </div>
                {error && (
                  <p className="field-message" id="si-error" role="alert">
                    {error}
                  </p>
                )}
                {auth.isDemo && (
                  <p className="demo-note" id="si-demo">
                    {t.siDemo(DEMO_CODE)}
                  </p>
                )}
                <div className="flow-actions">
                  <button type="submit" className="primary-button flow-primary" disabled={busy || code.length !== 6}>
                    {busy && <LoaderCircle className="spin" size={18} />}
                    {busy ? t.siVerifying : t.siVerify}
                  </button>
                  <button
                    type="button"
                    className="link-button"
                    disabled={resendIn > 0 || busy}
                    onClick={() => void sendCode()}
                  >
                    {resendIn > 0 ? t.siResendIn(resendIn) : t.siResend}
                  </button>
                </div>
              </form>
            )}
          </section>
          <p className="flow-escape">
            <Link to={returnTo}>{t.siSkip}</Link>
          </p>
        </div>
      </main>
    </div>
  );
}
