import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

/**
 * Interface copy in English and Hindi.
 *
 * Only the interface is translated. Facility names, addresses and evidence
 * quotes stay exactly as the source wrote them: a translated quote is no
 * longer evidence. Hindi copy should be reviewed by a native speaker before
 * launch; Odia and other regional languages slot in as another dictionary.
 */

export type Lang = "en" | "hi";

const en = {
  // header / chrome
  skipToSearch: "Skip to search",
  prototypeNote: "Prototype. Hospitals and sources shown are examples, not real listings.",
  liveNote: "Live data from Virtue Foundation facility records. Confirm with the hospital before you travel.",
  errService: "We didn't recognise that service.",
  errLocation: "We couldn't find that place.",
  errSearch: "The search didn't work.",
  errTry: "Try:",
  placeEmpty: "Type a district, city, 6-digit PIN code, or “lat, lon”.",
  emergency: "Medical emergency?",
  emergencyCall: "Call 108",
  navFind: "Find care",
  navHow: "How ranking works",
  homeLabel: "CarePath home",
  themeToDark: "Switch to dark theme",
  themeToLight: "Switch to light theme",
  menuOpen: "Open menu",
  menuClose: "Close menu",
  language: "Language",

  // hero
  raahiHello: "Namaste, I'm Raahi.",
  raahiIntro:
    "Tell me what care you need and where. I'll show you which hospitals offer it, and the proof.",
  heroTitle: "Find a hospital that offers the care you need.",
  heroLede:
    "We read hospital websites and government listings, and show you the proof behind every result.",

  // search
  careLabel: "Care you need",
  carePlaceholder: "e.g. kidney dialysis, MRI, NICU",
  placeLabel: "City, district or PIN code",
  placePlaceholder: "e.g. Bhubaneswar or 751012",
  distanceLabel: "Distance",
  within: (km: number) => `Within ${km} km`,
  find: "Find hospitals",
  finding: "Searching",
  useLocation: "Use my location",
  locationError: "We couldn't get your location. Type a city or PIN code instead.",
  currentLocation: "Current location",
  suggestionsServices: "Services",
  suggestionsPlaces: "Places",
  noServiceMatch: "Try “dialysis”, “MRI” or “NICU”.",
  commonSearches: "Common searches:",

  // results
  resultsTitle: (count: number, service: string, place: string) =>
    `${count} ${count === 1 ? "hospital offers" : "hospitals offer"} ${service.toLowerCase()} near ${place}`,
  resultsSearching: "Looking for hospitals",
  resultsContext: (km: number) =>
    `Within ${km} km. Ranked by how clearly the evidence shows they offer this service.`,
  sortBy: "Sort by",
  sortBest: "Best match",
  sortNearest: "Nearest",
  sortEvidence: "Most proof",
  filters: "Filters",
  filtersTitle: "Narrow results",
  reset: "Reset",
  maxDistance: "Maximum distance",
  highConfidenceOnly: "High confidence only",
  highConfidenceHint: "Backed by an official or government source",
  governmentOnly: "Government hospitals only",
  governmentHint: "Public hospitals usually cost less",
  viewList: "List",
  viewMap: "Map",
  loadingRaahi: "Finding hospitals…",
  emptyTitle: "No hospital with evidence for this service was found.",
  emptyBody: "Try a nearby city, or another name for the service.",
  clearFilters: "Clear filters",

  // card
  rank: (n: number) => `Rank ${n}`,
  matchScore: "match",
  scoreAria: (n: number) => `Match score ${n} out of 100`,
  kmAway: (km: string) => `${km} km away`,
  whyListed: "Why it's listed",
  strengthStrong: "Strong proof",
  strengthMedium: "Some proof",
  strengthWeak: "Weak proof",
  source: "Source",
  andMore: (n: number) => `and ${n} more`,
  seeProof: "See all proof",
  directions: "Directions",
  share: "WhatsApp",
  shareLabel: (name: string) => `Share ${name} on WhatsApp`,
  call: "Call",
  noPhone: "No phone number listed",
  confidenceHigh: "High confidence",
  confidenceMedium: "Medium confidence",
  confidenceLow: "Low confidence",
  operatorPublic: "Government",
  operatorPrivate: "Private",
  operatorTrust: "Charitable trust",

  // map
  mapTitle: "Map",
  mapLegend: "What the pin colours mean",
  legendStrong: "Strong match",
  legendMid: "Fair match",
  legendLow: "Weak match",
  mapCenter: "Back to search area",
  searchArea: "Your search area",
  mapNote: "Pins use the best location we could confirm.",
  openDetails: "Open details",

  // detail
  back: "Back to results",
  copy: "Copy summary",
  copied: "Copied",
  close: "Close",
  summary: "In short",
  scoreTitle: "How the score adds up",
  scoreModel: "Rules model v0.1",
  scoreService: "Offers this service",
  scoreEvidence: "Quality of proof",
  scoreSource: "Trust in sources",
  scoreDistance: "Distance",
  scoreLocation: "Location checked",
  scoreCapacity: "Capacity details",
  scorePenalty: "Deducted for weak proof",
  scoreDisclaimer:
    "The score sums up the signals the ranking uses. The order itself follows evidence-first rules: evidence, then distance, then how well the location is confirmed. Scores do not rate medical quality, safety or outcomes.",
  proofTitle: "The proof",
  items: (n: number) => `${n} ${n === 1 ? "item" : "items"}`,
  polarityPositive: "Supports",
  polarityUncertain: "Unclear",
  polarityNegative: "Contradicts",
  sourcesTitle: "Where it comes from",
  retrieved: "Checked on",
  sourceOfficial: "Hospital website",
  sourceGovernment: "Government listing",
  sourceDirectory: "Directory",
  sourceSocial: "Social media",
  sourceUnknown: "Other web page",
  unsureTitle: "What Raahi couldn't confirm",
  unsureHint: "Read this before you travel. Call the hospital first if you can.",
  missing: "Missing details:",
  detailFootnote:
    "CarePath compares public information. It is not medical advice and does not guarantee treatment is available.",

  // how it works
  howTitle: "How CarePath ranks hospitals",
  howLede:
    "A list is only useful if you can see why each place is on it. Every result shows its proof, and what we could not check.",
  howRaahi: "If we aren't sure, we will say so.",
  how1Title: "We match the care you asked for",
  how1Body: "Including other names for it, so “kidney machine” still finds dialysis.",
  how2Title: "We check where the hospital is",
  how2Body: "The address, PIN code and map location must agree before we show distance.",
  how3Title: "We read the proof",
  how3Body:
    "Hospital websites and government listings count for more than directories or social media.",
  how4Title: "We show what's missing",
  how4Body: "Old records, conflicting details and missing information stay visible on every card.",

  // emergency
  emergencyDoorTitle: "Emergency?",
  emergencyDoorBody: "Call 108 and see the nearest hospitals",
  emCall: "Call 108 for an ambulance",
  emCallHint: "Ambulance service, 24 hours",
  emNearest: "Nearest hospitals",
  emFrom: (place: string) => `Distances from ${place}`,
  emYourLocation: "your location",
  emLocating: "Finding your location…",
  emUseLocation: "Use my location",
  emBack: "Not an emergency? Search for care",
  emListFailed: "We couldn't load nearby hospitals. Call 108; the ambulance will take you to the right place.",

  // decision-first cards
  raahiAsk: "Namaste! What care do you need?",
  whyHospital: "Why this hospital?",
  reasonHigh: (sources: string) => `Confirmed by ${sources}`,
  reasonMedium: "Probably offers this. Some details aren't confirmed.",
  reasonLow: "Not confirmed. Call before you go.",
  and: "and",
  srcListOfficial: "the hospital's website",
  srcListGovernment: "a government listing",
  srcListDirectory: "a directory",
  srcListSocial: "social media",
  reasonWebOnly: "Mentioned on public web pages. Call to confirm before you go.",
  howToggle: "How we choose hospitals",

  // account & onboarding
  signIn: "Sign in",
  account: "Account",
  signedInAs: "Signed in as",
  signOut: "Sign out",
  editPreferences: "Change my preferences",
  setupPrompt: "First time here? Tell Raahi 5 things for faster results next time.",
  setupStart: "Set up in 30 seconds",
  setupDismiss: "Not now",
  obStep: (n: number, total: number) => `Step ${n} of ${total}`,
  obSkipAll: "Skip setup",
  obNext: "Next",
  obSkipQuestion: "Skip this question",
  obLangAsk: "Namaste! I'm Raahi. Which language would you like?",
  obLangHint: "You can change this any time at the top of the page.",
  obPlaceAsk: "Where do you usually look for care?",
  obPlaceHint: "I'll search here first. You can always search somewhere else.",
  obDistanceAsk: "How far can you travel for care?",
  obCostAsk: "Should I show government hospitals first?",
  obCostYes: "Yes, they usually cost less",
  obCostNo: "No, just show the best match",
  obContactAsk: "In an emergency, who should we call after 108?",
  obContactHint: "Saved only on this phone unless you sign in. We never call or message them.",
  obContactName: "Their name",
  obContactNamePlaceholder: "e.g. Ravi (son)",
  obContactPhone: "Their mobile number",
  obContactError: "Enter a 10-digit mobile number starting with 6, 7, 8 or 9.",
  obDoneTitle: "You're all set.",
  obDoneBody: "Next time, your results start from these answers.",
  obDoneFind: "Find care",
  obDoneSignIn: "Keep this on all your devices",
  obNotSet: "Not set",
  obSumPlace: "Usual place",
  obSumDistance: "Travel up to",
  obSumCost: "Government hospitals",
  obSumCostFirst: "Shown first",
  obSumCostNormal: "Mixed with others",
  obSumContact: "Emergency contact",
  callContact: (name: string) => `Call ${name}`,
  siTitle: "Sign in with your mobile number",
  siWhy: "Keeps your preferences and emergency contact on all your devices. You don't need an account to search.",
  siPhoneLabel: "Mobile number",
  siSendCode: "Send code",
  siSending: "Sending…",
  siPhoneError: "Enter a 10-digit mobile number starting with 6, 7, 8 or 9.",
  siCodeTitle: "Enter the 6-digit code",
  siCodeSent: (phone: string) => `We sent it by SMS to ${phone}.`,
  siChangeNumber: "Change number",
  siCodeLabel: "6-digit code",
  siVerify: "Sign in",
  siVerifying: "Checking…",
  siWrongCode: "That code didn't match. Check the SMS and try again.",
  siNetwork: "Couldn't reach CarePath. Check your connection and try again.",
  siResendIn: (s: number) => `Send a new code in ${s}s`,
  siResend: "Send a new code",
  siDemo: (code: string) => `Demo: no SMS is sent. Use the code ${code}.`,
  siSkip: "Continue without signing in",
  siDone: "You're signed in.",

  // sentence search & board
  searchTemplate: ["I need", "{service}", "near", "{place}", "{distance}", "."],
  raahiFill: "Namaste! Just fill in the blanks.",
  distanceAny: "at any distance",
  distanceWithin: (km: number) => `within ${km} km`,
  emergencyShort: "Emergency",
  topPick: "Your best option",
  topPickNearest: "Nearest to you",
  alsoNearby: "Other options",
  noneWithin: (km: number, nearest: string) =>
    `No hospital within ${km} km offers this. The nearest is ${nearest} km away.`,
  showUpTo: (km: number) => `Show hospitals up to ${km} km`,
  showAnyDistance: "Show all distances",
  noGovernment: "No government hospital was found for this search.",
  showAllHospitals: "Show all hospitals",
  obDistanceAny: "Any distance is fine",
  kmUnit: "km",

  // footer
  footerNote: "A research prototype. Not medical advice. In an emergency, call 108.",
  footerMethod: "How ranking works",
};

type Dict = typeof en;

const hi: Dict = {
  skipToSearch: "खोज पर जाएँ",
  prototypeNote: "प्रोटोटाइप। दिखाए गए अस्पताल और स्रोत उदाहरण हैं, असली सूची नहीं।",
  liveNote: "Virtue Foundation के अस्पताल रिकॉर्ड से असली डेटा। जाने से पहले अस्पताल से पुष्टि करें।",
  errService: "यह सेवा पहचान में नहीं आई।",
  errLocation: "यह जगह नहीं मिली।",
  errSearch: "खोज नहीं हो सकी।",
  errTry: "यह आज़माएँ:",
  placeEmpty: "ज़िला, शहर, 6 अंकों का पिन कोड या “lat, lon” लिखें।",
  emergency: "मेडिकल इमरजेंसी?",
  emergencyCall: "108 पर कॉल करें",
  navFind: "इलाज खोजें",
  navHow: "रैंकिंग कैसे होती है",
  homeLabel: "CarePath होम",
  themeToDark: "डार्क थीम चुनें",
  themeToLight: "लाइट थीम चुनें",
  menuOpen: "मेनू खोलें",
  menuClose: "मेनू बंद करें",
  language: "भाषा",

  raahiHello: "नमस्ते, मैं राही हूँ।",
  raahiIntro:
    "बताइए आपको कौन-सा इलाज चाहिए और कहाँ। मैं दिखाऊँगा कि कौन-से अस्पताल यह सेवा देते हैं, और उसका सबूत भी।",
  heroTitle: "ऐसा अस्पताल खोजें जहाँ आपको चाहिए वह इलाज मिले।",
  heroLede:
    "हम अस्पतालों की वेबसाइट और सरकारी सूचियाँ पढ़ते हैं, और हर नतीजे के पीछे का सबूत दिखाते हैं।",

  careLabel: "कौन-सा इलाज चाहिए",
  carePlaceholder: "जैसे किडनी डायलिसिस, MRI, NICU",
  placeLabel: "शहर, ज़िला या पिन कोड",
  placePlaceholder: "जैसे भुवनेश्वर या 751012",
  distanceLabel: "दूरी",
  within: (km) => `${km} किमी के अंदर`,
  find: "अस्पताल खोजें",
  finding: "खोज रहे हैं",
  useLocation: "मेरी लोकेशन लें",
  locationError: "आपकी लोकेशन नहीं मिल सकी। शहर या पिन कोड लिखें।",
  currentLocation: "मौजूदा लोकेशन",
  suggestionsServices: "सेवाएँ",
  suggestionsPlaces: "जगहें",
  noServiceMatch: "“डायलिसिस”, “MRI” या “NICU” लिखकर देखें।",
  commonSearches: "अक्सर खोजे गए:",

  resultsTitle: (count, service, place) => `${place} के पास ${count} अस्पताल ${service} की सेवा देते हैं`,
  resultsSearching: "अस्पताल खोज रहे हैं",
  resultsContext: (km) =>
    `${km} किमी के अंदर। क्रम इस पर आधारित है कि सबूत कितना साफ़ दिखाता है कि यह सेवा मिलती है।`,
  sortBy: "क्रम",
  sortBest: "सबसे सही",
  sortNearest: "सबसे पास",
  sortEvidence: "सबसे ज़्यादा सबूत",
  filters: "फ़िल्टर",
  filtersTitle: "नतीजे छाँटें",
  reset: "रीसेट",
  maxDistance: "अधिकतम दूरी",
  highConfidenceOnly: "सिर्फ़ पक्के नतीजे",
  highConfidenceHint: "आधिकारिक या सरकारी स्रोत से पुष्टि",
  governmentOnly: "सिर्फ़ सरकारी अस्पताल",
  governmentHint: "सरकारी अस्पतालों में आमतौर पर खर्च कम होता है",
  viewList: "सूची",
  viewMap: "नक्शा",
  loadingRaahi: "अस्पताल खोज रहे हैं…",
  emptyTitle: "इस सेवा के सबूत वाला कोई अस्पताल नहीं मिला।",
  emptyBody: "पास का कोई शहर, या सेवा का दूसरा नाम आज़माएँ।",
  clearFilters: "फ़िल्टर हटाएँ",

  rank: (n) => `क्रम ${n}`,
  matchScore: "मेल",
  scoreAria: (n) => `मेल स्कोर 100 में से ${n}`,
  kmAway: (km) => `${km} किमी दूर`,
  whyListed: "यह क्यों दिखाया गया",
  strengthStrong: "पक्का सबूत",
  strengthMedium: "कुछ सबूत",
  strengthWeak: "कमज़ोर सबूत",
  source: "स्रोत",
  andMore: (n) => `और ${n} अन्य`,
  seeProof: "पूरा सबूत देखें",
  directions: "रास्ता",
  share: "WhatsApp",
  shareLabel: (name) => `${name} को WhatsApp पर भेजें`,
  call: "कॉल करें",
  noPhone: "फ़ोन नंबर उपलब्ध नहीं",
  confidenceHigh: "पक्की जानकारी",
  confidenceMedium: "कुछ हद तक पक्की",
  confidenceLow: "कम पक्की",
  operatorPublic: "सरकारी",
  operatorPrivate: "निजी",
  operatorTrust: "धर्मार्थ ट्रस्ट",

  mapTitle: "नक्शा",
  mapLegend: "पिन के रंगों का मतलब",
  legendStrong: "अच्छा मेल",
  legendMid: "ठीक मेल",
  legendLow: "कमज़ोर मेल",
  mapCenter: "खोज वाले इलाके पर लौटें",
  searchArea: "आपका खोज इलाका",
  mapNote: "पिन सबसे पक्की मिली लोकेशन पर हैं।",
  openDetails: "जानकारी खोलें",

  back: "नतीजों पर लौटें",
  copy: "सारांश कॉपी करें",
  copied: "कॉपी हो गया",
  close: "बंद करें",
  summary: "संक्षेप में",
  scoreTitle: "स्कोर कैसे बना",
  scoreModel: "नियम मॉडल v0.1",
  scoreService: "यह सेवा देता है",
  scoreEvidence: "सबूत की गुणवत्ता",
  scoreSource: "स्रोत पर भरोसा",
  scoreDistance: "दूरी",
  scoreLocation: "लोकेशन की जाँच",
  scoreCapacity: "क्षमता की जानकारी",
  scorePenalty: "कमज़ोर सबूत के लिए कटौती",
  scoreDisclaimer:
    "स्कोर उन्हीं संकेतों का सार है जिनसे क्रम तय होता है। क्रम सबूत-पहले नियमों से बनता है: पहले सबूत, फिर दूरी, फिर लोकेशन कितनी पक्की है। स्कोर इलाज की गुणवत्ता, सुरक्षा या नतीजों को नहीं आँकता।",
  proofTitle: "सबूत",
  items: (n) => `${n} चीज़ें`,
  polarityPositive: "समर्थन करता है",
  polarityUncertain: "साफ़ नहीं",
  polarityNegative: "विरोध करता है",
  sourcesTitle: "जानकारी कहाँ से आई",
  retrieved: "जाँच की तारीख",
  sourceOfficial: "अस्पताल की वेबसाइट",
  sourceGovernment: "सरकारी सूची",
  sourceDirectory: "डायरेक्टरी",
  sourceSocial: "सोशल मीडिया",
  sourceUnknown: "अन्य वेब पेज",
  unsureTitle: "जो राही पक्का नहीं कर सका",
  unsureHint: "जाने से पहले इसे पढ़ें। हो सके तो पहले अस्पताल को फ़ोन करें।",
  missing: "जो जानकारी नहीं मिली:",
  detailFootnote:
    "CarePath सार्वजनिक जानकारी की तुलना करता है। यह डॉक्टरी सलाह नहीं है और इलाज मिलने की गारंटी नहीं देता।",

  howTitle: "CarePath अस्पतालों का क्रम कैसे तय करता है",
  howLede:
    "सूची तभी काम की है जब आप देख सकें कि हर अस्पताल उसमें क्यों है। हर नतीजा अपना सबूत दिखाता है, और वह भी जो हम जाँच नहीं सके।",
  howRaahi: "अगर हमें पक्का नहीं पता, तो हम साफ़ बताएँगे।",
  how1Title: "आपने जो इलाज माँगा, उससे मिलान",
  how1Body: "उसके दूसरे नामों से भी, ताकि “किडनी मशीन” लिखने पर भी डायलिसिस मिले।",
  how2Title: "अस्पताल कहाँ है, इसकी जाँच",
  how2Body: "दूरी दिखाने से पहले पता, पिन कोड और नक्शे की लोकेशन मेल खानी चाहिए।",
  how3Title: "सबूत पढ़ना",
  how3Body: "अस्पताल की वेबसाइट और सरकारी सूचियों को डायरेक्टरी या सोशल मीडिया से ज़्यादा महत्व मिलता है।",
  how4Title: "जो नहीं मिला, वह भी दिखाना",
  how4Body: "पुराने रिकॉर्ड, उलटी जानकारी और छूटी हुई बातें हर कार्ड पर दिखती हैं।",

  emergencyDoorTitle: "इमरजेंसी?",
  emergencyDoorBody: "108 पर कॉल करें और सबसे पास के अस्पताल देखें",
  emCall: "एम्बुलेंस के लिए 108 पर कॉल करें",
  emCallHint: "एम्बुलेंस सेवा, 24 घंटे",
  emNearest: "सबसे पास के अस्पताल",
  emFrom: (place) => `दूरी ${place} से`,
  emYourLocation: "आपकी लोकेशन",
  emLocating: "आपकी लोकेशन ढूँढ रहे हैं…",
  emUseLocation: "मेरी लोकेशन लें",
  emBack: "इमरजेंसी नहीं है? इलाज खोजें",
  emListFailed: "पास के अस्पताल लोड नहीं हो सके। 108 पर कॉल करें, एम्बुलेंस आपको सही जगह ले जाएगी।",

  raahiAsk: "नमस्ते! आपको कौन-सा इलाज चाहिए?",
  whyHospital: "यह अस्पताल क्यों?",
  reasonHigh: (sources) => `${sources} से पुष्टि हुई`,
  reasonMedium: "शायद यह सेवा मिलती है। कुछ बातें पक्की नहीं हैं।",
  reasonLow: "पुष्टि नहीं हुई। जाने से पहले फ़ोन करें।",
  and: "और",
  srcListOfficial: "अस्पताल की वेबसाइट",
  srcListGovernment: "सरकारी सूची",
  srcListDirectory: "डायरेक्टरी",
  srcListSocial: "सोशल मीडिया",
  reasonWebOnly: "सार्वजनिक वेब पेजों पर ज़िक्र है। जाने से पहले फ़ोन करके पुष्टि करें।",
  howToggle: "हम अस्पताल कैसे चुनते हैं",

  signIn: "साइन इन",
  account: "खाता",
  signedInAs: "इस नंबर से साइन इन",
  signOut: "साइन आउट",
  editPreferences: "मेरी पसंद बदलें",
  setupPrompt: "पहली बार आए हैं? राही को 5 बातें बताइए, अगली बार नतीजे जल्दी मिलेंगे।",
  setupStart: "30 सेकंड में सेट करें",
  setupDismiss: "अभी नहीं",
  obStep: (n, total) => `चरण ${n} / ${total}`,
  obSkipAll: "सेटअप छोड़ें",
  obNext: "आगे",
  obSkipQuestion: "यह सवाल छोड़ें",
  obLangAsk: "नमस्ते! मैं राही हूँ। आप कौन-सी भाषा चाहेंगे?",
  obLangHint: "इसे आप कभी भी पेज के ऊपर से बदल सकते हैं।",
  obPlaceAsk: "आप आमतौर पर कहाँ इलाज ढूँढते हैं?",
  obPlaceHint: "मैं पहले यहीं खोजूँगा। आप कहीं और भी खोज सकते हैं।",
  obDistanceAsk: "इलाज के लिए आप कितनी दूर जा सकते हैं?",
  obCostAsk: "क्या मैं सरकारी अस्पताल पहले दिखाऊँ?",
  obCostYes: "हाँ, उनमें आमतौर पर खर्च कम होता है",
  obCostNo: "नहीं, सबसे सही मेल दिखाएँ",
  obContactAsk: "इमरजेंसी में 108 के बाद किसे फ़ोन करें?",
  obContactHint: "साइन इन न करें तो यह सिर्फ़ इसी फ़ोन में रहता है। हम उन्हें कभी फ़ोन या मैसेज नहीं करते।",
  obContactName: "उनका नाम",
  obContactNamePlaceholder: "जैसे रवि (बेटा)",
  obContactPhone: "उनका मोबाइल नंबर",
  obContactError: "6, 7, 8 या 9 से शुरू होने वाला 10 अंकों का मोबाइल नंबर लिखें।",
  obDoneTitle: "सब तैयार है।",
  obDoneBody: "अगली बार आपके नतीजे इन्हीं जवाबों से शुरू होंगे।",
  obDoneFind: "इलाज खोजें",
  obDoneSignIn: "इसे अपने सभी डिवाइस पर रखें",
  obNotSet: "तय नहीं",
  obSumPlace: "आम जगह",
  obSumDistance: "अधिकतम दूरी",
  obSumCost: "सरकारी अस्पताल",
  obSumCostFirst: "पहले दिखेंगे",
  obSumCostNormal: "बाकियों के साथ",
  obSumContact: "इमरजेंसी संपर्क",
  callContact: (name) => `${name} को कॉल करें`,
  siTitle: "मोबाइल नंबर से साइन इन करें",
  siWhy: "आपकी पसंद और इमरजेंसी संपर्क आपके सभी डिवाइस पर रहते हैं। खोजने के लिए खाते की ज़रूरत नहीं।",
  siPhoneLabel: "मोबाइल नंबर",
  siSendCode: "कोड भेजें",
  siSending: "भेज रहे हैं…",
  siPhoneError: "6, 7, 8 या 9 से शुरू होने वाला 10 अंकों का मोबाइल नंबर लिखें।",
  siCodeTitle: "6 अंकों का कोड लिखें",
  siCodeSent: (phone) => `हमने ${phone} पर SMS भेजा है।`,
  siChangeNumber: "नंबर बदलें",
  siCodeLabel: "6 अंकों का कोड",
  siVerify: "साइन इन",
  siVerifying: "जाँच रहे हैं…",
  siWrongCode: "कोड मेल नहीं खाया। SMS देखकर फिर से कोशिश करें।",
  siNetwork: "CarePath से जुड़ नहीं सके। इंटरनेट देखकर फिर कोशिश करें।",
  siResendIn: (s) => `${s} सेकंड में नया कोड भेजें`,
  siResend: "नया कोड भेजें",
  siDemo: (code) => `डेमो: कोई SMS नहीं भेजा जाता। कोड ${code} लिखें।`,
  siSkip: "बिना साइन इन के आगे बढ़ें",
  siDone: "आप साइन इन हो गए।",

  searchTemplate: ["मुझे", "{place}", "के पास", "{distance}", "{service}", "चाहिए।"],
  raahiFill: "नमस्ते! बस खाली जगह भरिए।",
  distanceAny: "कितनी भी दूरी पर",
  distanceWithin: (km) => `${km} किमी के अंदर`,
  emergencyShort: "इमरजेंसी",
  topPick: "आपके लिए सबसे अच्छा",
  topPickNearest: "आपके सबसे पास",
  alsoNearby: "दूसरे विकल्प",
  noneWithin: (km, nearest) => `${km} किमी के अंदर कोई अस्पताल यह सेवा नहीं देता। सबसे पास वाला ${nearest} किमी दूर है।`,
  showUpTo: (km) => `${km} किमी तक के अस्पताल दिखाएँ`,
  showAnyDistance: "सभी दूरी दिखाएँ",
  noGovernment: "इस खोज में कोई सरकारी अस्पताल नहीं मिला।",
  showAllHospitals: "सभी अस्पताल दिखाएँ",
  obDistanceAny: "कोई भी दूरी चलेगी",
  kmUnit: "किमी",

  footerNote: "एक रिसर्च प्रोटोटाइप। डॉक्टरी सलाह नहीं। इमरजेंसी में 108 पर कॉल करें।",
  footerMethod: "रैंकिंग कैसे होती है",
};

const dictionaries: Record<Lang, Dict> = { en, hi };
const STORAGE_KEY = "carepath-lang";

function readSaved(): Lang {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    if (value === "en" || value === "hi") return value;
  } catch {
    /* storage unavailable */
  }
  // First visit: a Hindi browser gets Hindi; everyone else gets English.
  return navigator.language?.toLowerCase().startsWith("hi") ? "hi" : "en";
}

interface I18nValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Dict;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readSaved);

  useEffect(() => {
    document.documentElement.lang = lang === "hi" ? "hi" : "en-IN";
  }, [lang]);

  const setLang = useCallback((next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* the choice lasts for this visit only */
    }
  }, []);

  const value = useMemo(() => ({ lang, setLang, t: dictionaries[lang] }), [lang, setLang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (!value) throw new Error("useI18n must be used inside I18nProvider");
  return value;
}

/** Facility operator as a person would say it. */
export function operatorLabel(t: Dict, operator: string) {
  const key = operator.toLowerCase();
  if (key === "public" || key === "government") return t.operatorPublic;
  if (key === "private") return t.operatorPrivate;
  if (key === "trust") return t.operatorTrust;
  return operator;
}

export function isGovernment(operator: string) {
  const key = operator.toLowerCase();
  return key === "public" || key === "government";
}
