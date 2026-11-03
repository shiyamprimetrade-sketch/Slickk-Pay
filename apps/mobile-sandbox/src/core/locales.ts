/** Bangla/English application strings: translations describe sandbox behavior literally. */
import type {Locale,Operation,Status,SupportState,Persona} from "./types.js";
export type TranslationKey = keyof typeof english;
const english={
 appName:"Slickk Pay Lab",simulationBanner:"DEMO ONLY · FICTITIOUS MONEY",
 notReal:"Sample data only — no real accounts, banks or payments are connected.",
 noLiveTransfer:"Payments cannot be completed in this prototype.",home:"Home",activity:"Activity",
 agents:"Agents",notifications:"Notifications",settings:"Settings",support:"Support",
 dashboard:"Dashboard",customer:"Customer",agent:"Agent",merchant:"Merchant",
 sampleBalance:"Sample balance",availableFloat:"Fictional float",cashOnHand:"Sample physical cash",
 commission:"Illustrative commission",recentActivity:"Recent examples",sampleAgents:"Sample agent directory",
 findAgent:"Find an agent",serviceUnavailable:"Demo service unavailable",viewReceipt:"View sample receipt",
 previewQuote:"Preview fees",fee:"Proposed fee",principal:"Amount",total:"Total account debit",
 merchantFee:"Merchant fee",tax:"Tax (not verified)",commissionEarned:"Proposed commission",
 rateNotice:"Unapproved business hypothesis. Final taxes and network charges are not known.",
 quoteExpiry:"Quotes are local examples and cannot authorize a payment.",
 transfer:"Transfer",cashIn:"Cash in",cashOut:"Cash out",merchantPay:"Merchant pay",
 balanceInquiry:"Balance inquiry",amount:"Amount (BDT)",phone:"Bangladesh mobile number",
 payee:"Recipient",notes:"Note (optional)",prepare:"Prepare preview",review:"Review",
 notSent:"Not sent to a server",serverRequired:"Authoritative server confirmation is required.",
 invalidAmount:"Enter a valid amount",invalidPhone:"Enter a valid Bangladesh mobile number",
 selectAgent:"Choose a sample agent",agentUnavailable:"Sample agent is not accepting requests",
 insufficientSampleCash:"Fictional agent cash is below the sample request",
 insufficientSampleFloat:"Fictional float is below the sample request",
 requestReceipt:"Fictional receipt",ref:"Reference",status:"Status",date:"Date",
 completed:"Completed (fixture)",pending:"Pending (fixture)",failed:"Failed (fixture)",
 cancelled:"Cancelled (fixture)",reviewStatus:"Under review (fixture)",
 open:"Open",investigating:"Investigating",waiting:"Waiting",closed:"Closed",
 offline:"Offline",limited:"Limited network",online:"Online",viewingCache:"Showing local fictitious examples",
 staleWarning:"Not verified against any server. Never rely on this as a current balance.",
 reload:"Refresh example",noInternetPayments:"Offline payments are disabled.",
 security:"Security",privacy:"Privacy",lock:"Lock demo",unlock:"Unlock demo",
 sampleOnly:"Synthetic identity; not KYC-verified",maskedIdentity:"Identity is partly masked",
 neverSharePIN:"Never share your PIN, OTP or account password with an agent.",
 confirmNotAvailable:"Financial confirmation is intentionally unavailable.",
 riskHold:"Potential risk: preview may need manual review in a real system.",
 supportTitle:"Help and sample disputes",createCase:"Prepare support draft",
 description:"Description",subject:"Subject",category:"Category",
 sendDisabled:"No support ticket is sent from this demo.",
 suspicious:"Report suspicious activity",agreement:"I understand this is only a simulation",
 language:"Language",english:"English",bangla:"বাংলা",contrast:"High contrast",
 textScale:"Text size",accessibility:"Accessibility",next:"Next",back:"Back",
 close:"Close",cancel:"Cancel",clear:"Clear",search:"Search",all:"All",
 filter:"Filter",none:"None",unknown:"Unknown",optional:"Optional",required:"Required",
 profile:"Profile",signedOut:"Demo session locked",sessionExpired:"Demo session expired",
 noActualSettlement:"No actual bank settlement has been observed.",
 noDeposits:"This is not a bank deposit or insured balance.",noLoans:"Live credit is not available.",
 notAQRPayment:"QR preview cannot initiate a real payment.",
 receiptWarning:"Not proof of payment, cash handover, or settlement.",
 feeWarning:"Illustrative price. Regulatory/tax review required before use.",
 devices:"Device security",session:"Session",statement:"Activity statement",
 accountFrozen:"Sample account frozen",callAgent:"Agent contact is not provided in demo",
 merchantDashboard:"Sample merchant dashboard",agentDashboard:"Sample agent dashboard",
 disputed:"Dispute opened (fixture)",helpLine:"For emergencies, contact your licensed provider directly.",
 updateRequired:"Client update required",unsupported:"Feature not supported in sandbox",
 goHome:"Go home",accept:"Accept",decline:"Decline",stale:"Stale",
 auditTrail:"Illustrative audit",reconciliation:"Fictional reconciliation",
 previewOnly:"Preview only",noAuthority:"No authority to move funds",
 loginSample:"Select a synthetic persona to explore the lab.",signIn:"Enter demo",
 retry:"Retry",loading:"Loading",empty:"No samples match this filter",
 more:"More",showDetails:"Details",receiptCreated:"Draft receipt prepared",
};
const bangla:Record<TranslationKey,string>={
 appName:"স্লিক পে ল্যাব",simulationBanner:"শুধু ডেমো · কাল্পনিক টাকা",
 notReal:"শুধু নমুনা তথ্য — প্রকৃত ব্যাংক বা পেমেন্ট সংযুক্ত নয়।",
 noLiveTransfer:"এই প্রোটোটাইপে প্রকৃত লেনদেন সম্পন্ন করা যায় না।",home:"হোম",activity:"লেনদেনের নমুনা",
 agents:"এজেন্ট",notifications:"বিজ্ঞপ্তি",settings:"সেটিংস",support:"সহায়তা",
 dashboard:"ড্যাশবোর্ড",customer:"গ্রাহক",agent:"এজেন্ট",merchant:"ব্যবসায়ী",
 sampleBalance:"নমুনা ব্যালেন্স",availableFloat:"কাল্পনিক ফ্লোট",cashOnHand:"নমুনা নগদ",
 commission:"প্রস্তাবিত কমিশন",recentActivity:"সাম্প্রতিক উদাহরণ",sampleAgents:"নমুনা এজেন্ট তালিকা",
 findAgent:"এজেন্ট খুঁজুন",serviceUnavailable:"ডেমো সেবা উপলব্ধ নয়",viewReceipt:"নমুনা রসিদ দেখুন",
 previewQuote:"ফি দেখুন",fee:"প্রস্তাবিত ফি",principal:"পরিমাণ",total:"মোট ডেবিট",
 merchantFee:"ব্যবসায়ী ফি",tax:"কর (যাচাই করা হয়নি)",commissionEarned:"প্রস্তাবিত কমিশন",
 rateNotice:"এটি অনুমোদনহীন ব্যবসায়িক অনুমান। চূড়ান্ত কর ও নেটওয়ার্ক খরচ অজানা।",
 quoteExpiry:"এই হিসাব শুধু উদাহরণ; এটি লেনদেন অনুমোদন করতে পারে না।",
 transfer:"ট্রান্সফার",cashIn:"ক্যাশ ইন",cashOut:"ক্যাশ আউট",merchantPay:"ব্যবসায়ী পেমেন্ট",
 balanceInquiry:"ব্যালেন্স দেখা",amount:"পরিমাণ (টাকা)",phone:"বাংলাদেশি মোবাইল নম্বর",
 payee:"প্রাপক",notes:"নোট (ঐচ্ছিক)",prepare:"নমুনা তৈরি",review:"পর্যালোচনা",
 notSent:"সার্ভারে পাঠানো হয়নি",serverRequired:"সার্ভারের অনুমোদন আবশ্যক।",
 invalidAmount:"সঠিক পরিমাণ লিখুন",invalidPhone:"সঠিক মোবাইল নম্বর লিখুন",
 selectAgent:"নমুনা এজেন্ট নির্বাচন করুন",agentUnavailable:"নমুনা এজেন্ট অনুপলব্ধ",
 insufficientSampleCash:"নমুনা এজেন্টের নগদ যথেষ্ট নয়",insufficientSampleFloat:"নমুনা ফ্লোট যথেষ্ট নয়",
 requestReceipt:"কাল্পনিক রসিদ",ref:"রেফারেন্স",status:"অবস্থা",date:"তারিখ",
 completed:"সম্পন্ন (নমুনা)",pending:"অপেক্ষমান (নমুনা)",failed:"ব্যর্থ (নমুনা)",
 cancelled:"বাতিল (নমুনা)",reviewStatus:"পর্যালোচনাধীন (নমুনা)",
 open:"খোলা",investigating:"তদন্তাধীন",waiting:"অপেক্ষমান",closed:"বন্ধ",
 offline:"অফলাইন",limited:"সীমিত নেটওয়ার্ক",online:"অনলাইন",viewingCache:"স্থানীয় কাল্পনিক তথ্য দেখানো হচ্ছে",
 staleWarning:"সার্ভারে যাচাই করা হয়নি। বর্তমান ব্যালেন্স ধরে নেবেন না।",
 reload:"উদাহরণ রিফ্রেশ",noInternetPayments:"অফলাইনে পেমেন্ট বন্ধ।",
 security:"নিরাপত্তা",privacy:"গোপনীয়তা",lock:"ডেমো লক",unlock:"ডেমো আনলক",
 sampleOnly:"কাল্পনিক পরিচয়; কেওয়াইসি যাচাই করা নয়",maskedIdentity:"পরিচয় আংশিক লুকানো",
 neverSharePIN:"পিন, ওটিপি বা পাসওয়ার্ড এজেন্টকে দেবেন না।",
 confirmNotAvailable:"আর্থিক লেনদেন নিশ্চিত করার সুবিধা বন্ধ।",
 riskHold:"ঝুঁকি থাকলে প্রকৃত সেবায় মানবিক পর্যালোচনা দরকার।",
 supportTitle:"সহায়তা ও নমুনা বিরোধ",createCase:"সহায়তার খসড়া তৈরি",
 description:"বিবরণ",subject:"বিষয়",category:"ধরন",
 sendDisabled:"এই ডেমোতে অভিযোগ পাঠানো হয় না।",
 suspicious:"সন্দেহজনক কার্যক্রম জানান",agreement:"বুঝেছি, এটি কেবল সিমুলেশন",
 language:"ভাষা",english:"English",bangla:"বাংলা",contrast:"উচ্চ কনট্রাস্ট",
 textScale:"লেখার আকার",accessibility:"অ্যাক্সেসিবিলিটি",next:"পরবর্তী",back:"ফিরে যান",
 close:"বন্ধ",cancel:"বাতিল",clear:"মুছুন",search:"খুঁজুন",all:"সব",
 filter:"ফিল্টার",none:"কোনোটি নয়",unknown:"অজানা",optional:"ঐচ্ছিক",required:"আবশ্যক",
 profile:"প্রোফাইল",signedOut:"ডেমো সেশন লক হয়েছে",sessionExpired:"ডেমো সেশন শেষ",
 noActualSettlement:"বাস্তব ব্যাংক নিষ্পত্তি যাচাই করা হয়নি।",
 noDeposits:"এটি ব্যাংক আমানত বা বিমাকৃত ব্যালেন্স নয়।",noLoans:"প্রকৃত ঋণ সুবিধা নেই।",
 notAQRPayment:"কিউআর নমুনা দিয়ে প্রকৃত পেমেন্ট সম্ভব নয়।",
 receiptWarning:"এটি পেমেন্ট, নগদ হস্তান্তর বা নিষ্পত্তির প্রমাণ নয়।",
 feeWarning:"নমুনা মূল্য। ব্যবহার করার আগে আইন ও কর যাচাই জরুরি।",
 devices:"ডিভাইস নিরাপত্তা",session:"সেশন",statement:"লেনদেন বিবরণী",
 accountFrozen:"নমুনা অ্যাকাউন্ট স্থগিত",callAgent:"ডেমোতে যোগাযোগ তথ্য দেওয়া হয়নি",
 merchantDashboard:"নমুনা ব্যবসায়ী ড্যাশবোর্ড",agentDashboard:"নমুনা এজেন্ট ড্যাশবোর্ড",
 disputed:"বিরোধ খোলা (নমুনা)",helpLine:"জরুরি অবস্থায় আপনার অনুমোদিত সেবা প্রদানকারীর সঙ্গে যোগাযোগ করুন।",
 updateRequired:"অ্যাপ আপডেট দরকার",unsupported:"এই সুবিধা ডেমোতে নেই",
 goHome:"হোমে যান",accept:"গ্রহণ",decline:"না",stale:"পুরোনো",
 auditTrail:"নমুনা নিরীক্ষা",reconciliation:"কাল্পনিক মিলকরণ",
 previewOnly:"শুধু নমুনা",noAuthority:"টাকা স্থানান্তরের ক্ষমতা নেই",
 loginSample:"ডেমো দেখতে একটি কাল্পনিক পরিচয় নির্বাচন করুন।",signIn:"ডেমো খুলুন",
 retry:"আবার চেষ্টা",loading:"লোড হচ্ছে",empty:"কোনো নমুনা পাওয়া যায়নি",
 more:"আরও",showDetails:"বিস্তারিত",receiptCreated:"নমুনা রসিদ তৈরি হয়েছে",
};
export function t(locale:Locale,key:TranslationKey):string{return locale==="bn"?bangla[key]:english[key];}
export function operationLabel(locale:Locale,value:Operation):string{
 const keys:Record<Operation,TranslationKey>={transfer:"transfer",cash_in:"cashIn",cash_out:"cashOut",merchant_payment:"merchantPay",balance_inquiry:"balanceInquiry"};
 return t(locale,keys[value]);
}
export function statusLabel(locale:Locale,value:Status):string{
 const keys:Record<Status,TranslationKey>={completed:"completed",failed:"failed",cancelled:"cancelled",pending:"pending",review:"reviewStatus"};
 return t(locale,keys[value]);
}
export function caseStatusLabel(locale:Locale,value:SupportState):string{return t(locale,value);}
export function roleLabel(locale:Locale,value:Persona):string{return t(locale,value);}
export function localeDirection(_locale:Locale):"ltr" {return "ltr";}
export function availableLocales():readonly {code:Locale;label:string}[]{return [{code:"en",label:"English"},{code:"bn",label:"বাংলা"}];}
export function validateTranslations():readonly string[]{
 const issues:string[]=[];
 for(const key of Object.keys(english) as TranslationKey[]){
  if(!bangla[key]||!bangla[key].trim())issues.push(`MISSING_BN:${key}`);
  if(!english[key].trim())issues.push(`MISSING_EN:${key}`);
 }
 for(const key of Object.keys(bangla)){if(!(key in english))issues.push(`EXTRA_BN:${key}`);}
 return Object.freeze(issues);
}
export function pluralCount(locale:Locale,count:number,word:string):string{
 if(!Number.isSafeInteger(count)||count<0)throw new Error("INVALID_COUNT");
 return locale==="bn"?`${new Intl.NumberFormat("bn-BD").format(count)} ${word}`:`${count} ${word}${count===1?"":"s"}`;
}
export function localTime(locale:Locale,iso:string):string{
 const n=Date.parse(iso);
 if(!Number.isFinite(n))return t(locale,"unknown");
 return new Intl.DateTimeFormat(locale==="bn"?"bn-BD":"en-BD",{timeZone:"Asia/Dhaka",dateStyle:"medium",timeStyle:"short"}).format(new Date(n));
}
export function statusColor(value:Status):"neutral"|"positive"|"danger"|"warning"{
 if(value==="completed")return "positive";
 if(value==="failed"||value==="cancelled")return "danger";
 if(value==="review")return "warning";
 return "neutral";
}
export function isBangla(locale:Locale):boolean{return locale==="bn";}
export function flipLocale(locale:Locale):Locale{return locale==="en"?"bn":"en";}
