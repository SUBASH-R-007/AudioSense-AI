"""Patient-counseling phrases in the major languages of southern India.

The counseling sheet is written at roughly an 8th-grade reading level and
translated into the languages patients actually speak at home. Each entry
maps one clinical concept to a plain-language sentence; the report engine
interpolates patient specifics around them.

Only fixed, pre-authored strings live here — no machine translation at
runtime — so the wording is stable and reviewable.
"""
from __future__ import annotations

LANGUAGES = {
    "english": {"label": "English", "native": "English", "tts": "en-IN"},
    "tamil": {"label": "Tamil", "native": "தமிழ்", "tts": "ta-IN"},
    "hindi": {"label": "Hindi", "native": "हिन्दी", "tts": "hi-IN"},
    "telugu": {"label": "Telugu", "native": "తెలుగు", "tts": "te-IN"},
    "kannada": {"label": "Kannada", "native": "ಕನ್ನಡ", "tts": "kn-IN"},
    "malayalam": {"label": "Malayalam", "native": "മലയാളം", "tts": "ml-IN"},
}

#: Degree of loss, in plain language, per WHO grade.
GRADE_SIMPLE = {
    "english": {
        "Normal hearing": "normal",
        "Mild hearing loss": "slightly reduced",
        "Moderate hearing loss": "moderately reduced",
        "Moderately severe hearing loss": "quite reduced",
        "Severe hearing loss": "severely reduced",
        "Profound hearing loss": "very severely reduced",
    },
    "tamil": {
        "Normal hearing": "இயல்பாக உள்ளது",
        "Mild hearing loss": "லேசாகக் குறைந்துள்ளது",
        "Moderate hearing loss": "மிதமாகக் குறைந்துள்ளது",
        "Moderately severe hearing loss": "கணிசமாகக் குறைந்துள்ளது",
        "Severe hearing loss": "கடுமையாகக் குறைந்துள்ளது",
        "Profound hearing loss": "மிகக் கடுமையாகக் குறைந்துள்ளது",
    },
    "hindi": {
        "Normal hearing": "सामान्य है",
        "Mild hearing loss": "थोड़ी कम है",
        "Moderate hearing loss": "मध्यम रूप से कम है",
        "Moderately severe hearing loss": "काफी कम है",
        "Severe hearing loss": "बहुत कम है",
        "Profound hearing loss": "अत्यधिक कम है",
    },
    "telugu": {
        "Normal hearing": "సాధారణంగా ఉంది",
        "Mild hearing loss": "కొద్దిగా తగ్గింది",
        "Moderate hearing loss": "మధ్యస్థంగా తగ్గింది",
        "Moderately severe hearing loss": "గణనీయంగా తగ్గింది",
        "Severe hearing loss": "తీవ్రంగా తగ్గింది",
        "Profound hearing loss": "చాలా తీవ్రంగా తగ్గింది",
    },
    "kannada": {
        "Normal hearing": "ಸಾಮಾನ್ಯವಾಗಿದೆ",
        "Mild hearing loss": "ಸ್ವಲ್ಪ ಕಡಿಮೆಯಾಗಿದೆ",
        "Moderate hearing loss": "ಮಧ್ಯಮ ಪ್ರಮಾಣದಲ್ಲಿ ಕಡಿಮೆಯಾಗಿದೆ",
        "Moderately severe hearing loss": "ಗಣನೀಯವಾಗಿ ಕಡಿಮೆಯಾಗಿದೆ",
        "Severe hearing loss": "ತೀವ್ರವಾಗಿ ಕಡಿಮೆಯಾಗಿದೆ",
        "Profound hearing loss": "ಅತಿ ತೀವ್ರವಾಗಿ ಕಡಿಮೆಯಾಗಿದೆ",
    },
    "malayalam": {
        "Normal hearing": "സാധാരണമാണ്",
        "Mild hearing loss": "അല്പം കുറഞ്ഞിട്ടുണ്ട്",
        "Moderate hearing loss": "മിതമായി കുറഞ്ഞിട്ടുണ്ട്",
        "Moderately severe hearing loss": "ഗണ്യമായി കുറഞ്ഞിട്ടുണ്ട്",
        "Severe hearing loss": "ഗുരുതരമായി കുറഞ്ഞിട്ടുണ്ട്",
        "Profound hearing loss": "വളരെ ഗുരുതരമായി കുറഞ്ഞിട്ടുണ്ട്",
    },
}

#: "Your {side} ear hearing is {grade}."
EAR_SENTENCE = {
    "english": "Your {side} ear hearing is {grade}.",
    "tamil": "உங்கள் {side} காதின் கேட்கும் திறன் {grade}.",
    "hindi": "आपके {side} कान की सुनने की क्षमता {grade}.",
    "telugu": "మీ {side} చెవి వినికిడి శక్తి {grade}.",
    "kannada": "ನಿಮ್ಮ {side} ಕಿವಿಯ ಶ್ರವಣ ಶಕ್ತಿ {grade}.",
    "malayalam": "നിങ്ങളുടെ {side} ചെവിയുടെ കേൾവി {grade}.",
}

SIDE_WORD = {
    "english": {"right": "right", "left": "left"},
    "tamil": {"right": "வலது", "left": "இடது"},
    "hindi": {"right": "दाहिने", "left": "बाएँ"},
    "telugu": {"right": "కుడి", "left": "ఎడమ"},
    "kannada": {"right": "ಬಲ", "left": "ಎಡ"},
    "malayalam": {"right": "വലത്", "left": "ഇടത്"},
}

HEARING_AID = {
    "english": "A hearing aid can help you hear conversations more easily — "
               "please meet an audiologist to try one.",
    "tamil": "செவிப்புலன் கருவி (hearing aid) உரையாடல்களை எளிதாகக் கேட்க உதவும் — "
             "காதியல் நிபுணரை (audiologist) அணுகவும்.",
    "hindi": "सुनने की मशीन (hearing aid) से बातचीत सुनना आसान हो सकता है — "
             "कृपया ऑडियोलॉजिस्ट से मिलकर इसे आज़माएँ।",
    "telugu": "వినికిడి యంత్రం (hearing aid) సంభాషణలు సులభంగా వినడానికి సహాయపడుతుంది — "
              "దయచేసి ఆడియాలజిస్ట్‌ను కలిసి ప్రయత్నించండి.",
    "kannada": "ಶ್ರವಣ ಸಾಧನ (hearing aid) ಸಂಭಾಷಣೆಗಳನ್ನು ಸುಲಭವಾಗಿ ಕೇಳಲು ಸಹಾಯ ಮಾಡುತ್ತದೆ — "
               "ದಯವಿಟ್ಟು ಆಡಿಯಾಲಜಿಸ್ಟ್ ಅವರನ್ನು ಭೇಟಿ ಮಾಡಿ.",
    "malayalam": "ശ്രവണ സഹായി (hearing aid) സംഭാഷണങ്ങൾ എളുപ്പത്തിൽ കേൾക്കാൻ സഹായിക്കും — "
                 "ദയവായി ഒരു ഓഡിയോളജിസ്റ്റിനെ കാണുക.",
}

BENCHMARK = {
    "english": "Your hearing disability is {pct}%, which is above 40%. You may be "
               "eligible for a government disability certificate and benefits.",
    "tamil": "உங்கள் செவித்திறன் குறைபாடு {pct}% — இது 40%-க்கு மேல் இருப்பதால், அரசு "
             "மாற்றுத்திறனாளர் சான்றிதழ் மற்றும் நலத்திட்ட உதவிகளுக்கு நீங்கள் தகுதி பெறலாம்.",
    "hindi": "आपकी श्रवण दिव्यांगता {pct}% है, जो 40% से अधिक है। आप सरकारी दिव्यांगता "
             "प्रमाण पत्र और लाभों के पात्र हो सकते हैं।",
    "telugu": "మీ వినికిడి వైకల్యం {pct}% — ఇది 40% కంటే ఎక్కువ. మీరు ప్రభుత్వ వైకల్య "
              "ధ్రువీకరణ పత్రం మరియు ప్రయోజనాలకు అర్హులు కావచ్చు.",
    "kannada": "ನಿಮ್ಮ ಶ್ರವಣ ವಿಕಲತೆ {pct}% — ಇದು 40%ಕ್ಕಿಂತ ಹೆಚ್ಚು. ನೀವು ಸರ್ಕಾರಿ ವಿಕಲಚೇತನ "
               "ಪ್ರಮಾಣಪತ್ರ ಮತ್ತು ಸೌಲಭ್ಯಗಳಿಗೆ ಅರ್ಹರಾಗಬಹುದು.",
    "malayalam": "നിങ്ങളുടെ കേൾവി വൈകല്യം {pct}% ആണ് — ഇത് 40%-ൽ കൂടുതലാണ്. സർക്കാർ "
                 "ഭിന്നശേഷി സർട്ടിഫിക്കറ്റിനും ആനുകൂല്യങ്ങൾക്കും നിങ്ങൾ അർഹരാകാം.",
}

URGENT = {
    "english": "IMPORTANT: your test shows a finding that needs a doctor's attention "
               "soon. Please see an ENT specialist without delay.",
    "tamil": "முக்கியம்: உங்கள் பரிசோதனையில் மருத்துவரின் உடனடி கவனம் தேவைப்படும் ஒரு "
             "விஷயம் தெரிகிறது. தாமதிக்காமல் ENT மருத்துவரை அணுகவும்.",
    "hindi": "महत्वपूर्ण: आपकी जाँच में ऐसी बात मिली है जिस पर डॉक्टर का ध्यान जल्दी "
             "चाहिए। कृपया बिना देरी ENT विशेषज्ञ से मिलें।",
    "telugu": "ముఖ్యం: మీ పరీక్షలో వైద్యుని దృష్టి త్వరగా అవసరమయ్యే విషయం కనిపించింది. "
              "ఆలస్యం చేయకుండా ENT వైద్యుడిని సంప్రదించండి.",
    "kannada": "ಮುಖ್ಯ: ನಿಮ್ಮ ಪರೀಕ್ಷೆಯಲ್ಲಿ ವೈದ್ಯರ ಗಮನ ಶೀಘ್ರವಾಗಿ ಬೇಕಾದ ಅಂಶ ಕಂಡುಬಂದಿದೆ. "
               "ವಿಳಂಬ ಮಾಡದೆ ENT ತಜ್ಞರನ್ನು ಭೇಟಿ ಮಾಡಿ.",
    "malayalam": "പ്രധാനം: നിങ്ങളുടെ പരിശോധനയിൽ ഡോക്ടറുടെ ശ്രദ്ധ ഉടൻ വേണ്ട ഒരു കാര്യം "
                 "കണ്ടെത്തി. കാലതാമസം കൂടാതെ ENT ഡോക്ടറെ കാണുക.",
}

TIPS = {
    "english": [
        "Face the person you are talking with — seeing lips and expressions helps a lot.",
        "Reduce background noise (TV, fan) during conversations.",
        "Ask people to speak clearly and a little slower, not to shout.",
        "Protect your ears from loud noise; use earplugs or earmuffs in noisy places.",
        "Get your hearing tested again every 6–12 months.",
    ],
    "tamil": [
        "பேசுபவரின் முகத்தைப் பார்த்து உரையாடுங்கள் — உதடுகளும் முகபாவனைகளும் புரிந்துகொள்ள உதவும்.",
        "உரையாடும்போது பின்னணி சத்தத்தை (டிவி, மின்விசிறி) குறைத்துக் கொள்ளுங்கள்.",
        "சத்தமாகக் கத்த வேண்டாம்; தெளிவாக, சற்று மெதுவாகப் பேசச் சொல்லுங்கள்.",
        "அதிக சத்தத்திலிருந்து காதுகளைப் பாதுகாக்கவும்; சத்தமான இடங்களில் காது காப்பான்கள் அணியவும்.",
        "ஒவ்வொரு 6–12 மாதங்களுக்கும் ஒருமுறை கேட்புத் திறன் பரிசோதனை செய்யுங்கள்.",
    ],
    "hindi": [
        "जिससे बात कर रहे हैं उसका चेहरा देखें — होंठ और भाव समझने में बहुत मदद करते हैं।",
        "बातचीत के समय पृष्ठभूमि का शोर (टीवी, पंखा) कम करें।",
        "लोगों से कहें कि साफ़ और थोड़ा धीरे बोलें, चिल्लाएँ नहीं।",
        "तेज़ आवाज़ से कान बचाएँ; शोरगुल वाली जगह पर इयरप्लग या इयरमफ़ पहनें।",
        "हर 6–12 महीने में सुनने की जाँच दोबारा कराएँ।",
    ],
    "telugu": [
        "మాట్లాడే వ్యక్తి ముఖం చూస్తూ మాట్లాడండి — పెదవులు, ముఖ కవళికలు అర్థం చేసుకోవడానికి సహాయపడతాయి.",
        "సంభాషణ సమయంలో నేపథ్య శబ్దాన్ని (టీవీ, ఫ్యాన్) తగ్గించండి.",
        "అరవవద్దని, స్పష్టంగా కొద్దిగా నెమ్మదిగా మాట్లాడమని చెప్పండి.",
        "పెద్ద శబ్దాల నుండి చెవులను కాపాడుకోండి; శబ్దం ఉన్న చోట ఇయర్‌ప్లగ్‌లు వాడండి.",
        "ప్రతి 6–12 నెలలకు ఒకసారి వినికిడి పరీక్ష చేయించుకోండి.",
    ],
    "kannada": [
        "ಮಾತನಾಡುವವರ ಮುಖವನ್ನು ನೋಡುತ್ತಾ ಮಾತನಾಡಿ — ತುಟಿ ಮತ್ತು ಮುಖಭಾವ ಅರ್ಥಮಾಡಿಕೊಳ್ಳಲು ಸಹಾಯ ಮಾಡುತ್ತದೆ.",
        "ಸಂಭಾಷಣೆಯ ಸಮಯದಲ್ಲಿ ಹಿನ್ನೆಲೆ ಶಬ್ದವನ್ನು (ಟಿವಿ, ಫ್ಯಾನ್) ಕಡಿಮೆ ಮಾಡಿ.",
        "ಕಿರುಚದೆ, ಸ್ಪಷ್ಟವಾಗಿ ಸ್ವಲ್ಪ ನಿಧಾನವಾಗಿ ಮಾತನಾಡಲು ಹೇಳಿ.",
        "ದೊಡ್ಡ ಶಬ್ದದಿಂದ ಕಿವಿಗಳನ್ನು ರಕ್ಷಿಸಿ; ಗದ್ದಲದ ಸ್ಥಳಗಳಲ್ಲಿ ಇಯರ್‌ಪ್ಲಗ್ ಬಳಸಿ.",
        "ಪ್ರತಿ 6–12 ತಿಂಗಳಿಗೊಮ್ಮೆ ಶ್ರವಣ ಪರೀಕ್ಷೆ ಮಾಡಿಸಿ.",
    ],
    "malayalam": [
        "സംസാരിക്കുന്ന ആളുടെ മുഖം നോക്കി സംസാരിക്കുക — ചുണ്ടുകളും ഭാവങ്ങളും മനസ്സിലാക്കാൻ സഹായിക്കും.",
        "സംഭാഷണ സമയത്ത് പശ്ചാത്തല ശബ്ദം (ടിവി, ഫാൻ) കുറയ്ക്കുക.",
        "വിളിച്ചുകൂവാതെ, വ്യക്തമായി അല്പം പതുക്കെ സംസാരിക്കാൻ പറയുക.",
        "ഉച്ചത്തിലുള്ള ശബ്ദത്തിൽ നിന്ന് ചെവി സംരക്ഷിക്കുക; ശബ്ദമുള്ള സ്ഥലങ്ങളിൽ ഇയർപ്ലഗ് ഉപയോഗിക്കുക.",
        "ഓരോ 6–12 മാസത്തിലും കേൾവി പരിശോധന നടത്തുക.",
    ],
}

HEADING = {
    "english": "Hearing Summary for {name}",
    "tamil": "{name} — கேட்புத் திறன் சுருக்கம்",
    "hindi": "{name} — श्रवण सारांश",
    "telugu": "{name} — వినికిడి సారాంశం",
    "kannada": "{name} — ಶ್ರವಣ ಸಾರಾಂಶ",
    "malayalam": "{name} — കേൾവി സംഗ്രഹം",
}

TIPS_HEADING = {
    "english": "Practical tips",
    "tamil": "நடைமுறை குறிப்புகள்",
    "hindi": "व्यावहारिक सुझाव",
    "telugu": "ఆచరణాత్మక సూచనలు",
    "kannada": "ಪ್ರಾಯೋಗಿಕ ಸಲಹೆಗಳು",
    "malayalam": "പ്രായോഗിക നിർദ്ദേശങ്ങൾ",
}
