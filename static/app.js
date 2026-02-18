const API_BASE = '';
let symptoms = [];
let medicalHistory = [];
let medications = [];
let currentSessionId = null;
let currentStep = 1;

// --- Tag Management ---

function createTag(text, containerId, removeCallback) {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.innerHTML = `${escapeHtml(text)} <button class="remove-tag" onclick="this.parentElement.remove(); ${removeCallback}('${escapeHtml(text)}')">&times;</button>`;
    document.getElementById(containerId).appendChild(tag);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function addSymptom() {
    const input = document.getElementById('symptom-input');
    const val = input.value.trim();
    if (val && !symptoms.includes(val)) {
        symptoms.push(val);
        createTag(val, 'symptoms-tags', 'removeSymptom');
    }
    input.value = '';
    input.focus();
}

function removeSymptom(val) {
    symptoms = symptoms.filter(s => s !== val);
}

function addQuickSymptom(val) {
    if (!symptoms.includes(val)) {
        symptoms.push(val);
        createTag(val, 'symptoms-tags', 'removeSymptom');
    }
}

function addHistory() {
    const input = document.getElementById('history-input');
    const val = input.value.trim();
    if (val && !medicalHistory.includes(val)) {
        medicalHistory.push(val);
        createTag(val, 'history-tags', 'removeHistory');
    }
    input.value = '';
    input.focus();
}

function removeHistory(val) {
    medicalHistory = medicalHistory.filter(h => h !== val);
}

function addQuickHistory(val) {
    if (!medicalHistory.includes(val)) {
        medicalHistory.push(val);
        createTag(val, 'history-tags', 'removeHistory');
    }
}

function addMedication() {
    const input = document.getElementById('medication-input');
    const val = input.value.trim();
    if (val && !medications.includes(val)) {
        medications.push(val);
        createTag(val, 'medication-tags', 'removeMedication');
    }
    input.value = '';
    input.focus();
}

function removeMedication(val) {
    medications = medications.filter(m => m !== val);
}

// --- Enter key support ---

document.addEventListener('DOMContentLoaded', () => {
    const handlers = [
        ['symptom-input', addSymptom],
        ['history-input', addHistory],
        ['medication-input', addMedication],
    ];
    handlers.forEach(([id, fn]) => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('keypress', e => { if (e.key === 'Enter') { e.preventDefault(); fn(); } });
    });
});

// --- Step Navigation ---

function nextStep(step) {
    if (step === 2 && symptoms.length === 0) {
        alert('Please add at least one symptom.');
        return;
    }

    document.querySelectorAll('.form-step').forEach(s => s.classList.remove('active'));
    document.getElementById(`step-${step}`).classList.add('active');

    document.querySelectorAll('.step').forEach(s => {
        const sStep = parseInt(s.dataset.step);
        s.classList.remove('active', 'completed');
        if (sStep === step) s.classList.add('active');
        else if (sStep < step) s.classList.add('completed');
    });

    document.querySelectorAll('.step-line').forEach((line, idx) => {
        line.classList.toggle('active', idx < step - 1);
    });

    currentStep = step;
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

// --- Lab Reports ---

function addLabRow() {
    const container = document.getElementById('lab-reports-container');
    const row = document.createElement('div');
    row.className = 'lab-row';
    row.innerHTML = `
        <input type="text" class="lab-name" placeholder="e.g., HbA1c">
        <input type="text" class="lab-value" placeholder="e.g., 7.2%">
        <input type="text" class="lab-when" placeholder="e.g., Today, 2 weeks ago">
        <button type="button" class="btn-icon btn-danger" onclick="removeLabRow(this)"><i class="fas fa-times"></i></button>
    `;
    container.appendChild(row);
}

function removeLabRow(btn) {
    const rows = document.querySelectorAll('#lab-reports-container .lab-row');
    if (rows.length > 1) btn.closest('.lab-row').remove();
    else {
        btn.closest('.lab-row').querySelectorAll('input').forEach(i => i.value = '');
    }
}

// --- Build Request ---

function buildRequest() {
    const req = { symptoms };

    const duration = document.getElementById('duration').value.trim();
    if (duration) req.symptom_duration = duration;

    const notes = document.getElementById('additional-notes').value.trim();
    if (notes) req.additional_notes = notes;

    const age = document.getElementById('age').value;
    const gender = document.getElementById('gender').value;
    const weight = document.getElementById('weight').value;
    const height = document.getElementById('height').value;
    if (age || gender || weight || height) {
        req.patient_info = {};
        if (age) req.patient_info.age = parseInt(age);
        if (gender) req.patient_info.gender = gender;
        if (weight) req.patient_info.weight_kg = parseFloat(weight);
        if (height) req.patient_info.height_cm = parseFloat(height);
    }

    if (medicalHistory.length > 0) req.medical_history = medicalHistory;
    if (medications.length > 0) req.current_medications = medications;

    const lifestyle = document.getElementById('lifestyle').value.trim();
    if (lifestyle) req.lifestyle = lifestyle;

    const bpSys = document.getElementById('bp-systolic').value;
    const bpDia = document.getElementById('bp-diastolic').value;
    const hr = document.getElementById('heart-rate').value;
    const temp = document.getElementById('temperature').value;
    const rr = document.getElementById('respiratory-rate').value;
    const spo2 = document.getElementById('spo2').value;
    if (bpSys || bpDia || hr || temp || rr || spo2) {
        req.vitals = {};
        if (bpSys) req.vitals.blood_pressure_systolic = parseInt(bpSys);
        if (bpDia) req.vitals.blood_pressure_diastolic = parseInt(bpDia);
        if (hr) req.vitals.heart_rate = parseInt(hr);
        if (temp) req.vitals.temperature_f = parseFloat(temp);
        if (rr) req.vitals.respiratory_rate = parseInt(rr);
        if (spo2) req.vitals.oxygen_saturation = parseFloat(spo2);
    }

    const labRows = document.querySelectorAll('#lab-reports-container .lab-row');
    const labs = [];
    labRows.forEach(row => {
        const name = row.querySelector('.lab-name').value.trim();
        const value = row.querySelector('.lab-value').value.trim();
        const when = row.querySelector('.lab-when') ? row.querySelector('.lab-when').value.trim() : '';
        if (name && value) {
            const lab = { name, value };
            if (when) lab.when = when;
            labs.push(lab);
        }
    });
    if (labs.length > 0) req.lab_reports = labs;

    if (currentSessionId) req.session_id = currentSessionId;

    return req;
}

// --- Error Toast ---

function showErrorToast(title, detail, duration = 8000) {
    document.querySelectorAll('.error-toast').forEach(t => t.remove());

    const toast = document.createElement('div');
    toast.className = 'error-toast';
    toast.innerHTML = `
        <i class="fas fa-exclamation-circle"></i>
        <div class="toast-message">
            <div class="toast-title">${escapeHtml(title)}</div>
            <div class="toast-detail">${escapeHtml(detail)}</div>
        </div>
        <button class="toast-close" onclick="this.parentElement.remove()">&times;</button>
    `;
    document.body.appendChild(toast);
    if (duration > 0) setTimeout(() => toast.remove(), duration);
}

// --- Submit Diagnosis ---

async function submitDiagnosis() {
    if (symptoms.length === 0) {
        showErrorToast('Missing Symptoms', 'Please add at least one symptom before analyzing.');
        nextStep(1);
        return;
    }

    nextStep(4);
    document.getElementById('loading-section').style.display = 'block';
    document.getElementById('results-section').style.display = 'none';

    const req = buildRequest();

    try {
        const res = await fetch(`${API_BASE}/api/diagnose`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(req),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
            if (res.status === 429) {
                throw { title: 'Rate Limit Reached', message: err.detail || 'The AI service is temporarily rate-limited. Please wait 1-2 minutes and try again.' };
            }
            throw { title: 'Analysis Failed', message: err.detail || `Server error (${res.status})` };
        }

        const data = await res.json();
        currentSessionId = data.session_id;
        renderResults(data);
    } catch (err) {
        document.getElementById('loading-section').style.display = 'none';
        if (err.title) {
            showErrorToast(err.title, err.message, 12000);
        } else {
            showErrorToast('Connection Error', err.message || 'Could not reach the server. Please check if the backend is running.');
        }
        nextStep(3);
    }
}

// --- Render Results ---

function renderResults(data) {
    document.getElementById('loading-section').style.display = 'none';
    document.getElementById('results-section').style.display = 'block';

    renderUrgency(data.urgency_level, data.urgency_reasoning);
    renderPredictions(data.predictions);
    renderTests(data.recommended_tests);
    renderSpecialists(data.recommended_specialists);
    renderAdvice(data.general_advice);
    renderFollowUp(data.follow_up_questions || data.additional_questions || []);
    document.getElementById('result-disclaimer').textContent = data.disclaimer;
}

function renderUrgency(level, reasoning) {
    const banner = document.getElementById('urgency-banner');
    banner.className = `urgency-banner urgency-${level}`;

    const icons = { low: 'check-circle', moderate: 'exclamation-circle', high: 'exclamation-triangle', critical: 'skull-crossbones' };
    const labels = { low: 'Low Urgency', moderate: 'Moderate Urgency', high: 'High Urgency', critical: 'Critical - Seek Immediate Care' };

    banner.querySelector('i').className = `fas fa-${icons[level] || 'exclamation-circle'}`;
    document.getElementById('urgency-level-text').textContent = labels[level] || level;
    document.getElementById('urgency-reasoning').textContent = reasoning;
}

function renderPredictions(predictions) {
    const container = document.getElementById('predictions-container');
    container.innerHTML = '';

    predictions.forEach((p, idx) => {
        const conf = p.confidence;
        const level = conf >= 0.7 ? 'high' : conf >= 0.4 ? 'medium' : 'low';
        const barColor = conf >= 0.7 ? 'var(--danger)' : conf >= 0.4 ? 'var(--warning)' : 'var(--success)';

        const item = document.createElement('div');
        item.className = `prediction-item confidence-${level}`;
        item.innerHTML = `
            <div class="prediction-header">
                <div class="prediction-name">${idx + 1}. ${escapeHtml(p.disease)}</div>
                <div class="confidence-badge confidence-${level}">
                    <i class="fas fa-chart-bar"></i> ${(conf * 100).toFixed(0)}% confidence
                </div>
            </div>
            <div class="prediction-description">${escapeHtml(p.description)}</div>
            <div class="matching-factors">
                ${p.key_matching_factors.map(f => `<span class="factor-tag"><i class="fas fa-check" style="color: var(--success); margin-right: 3px;"></i>${escapeHtml(f)}</span>`).join('')}
            </div>
            <div class="confidence-bar-bg">
                <div class="confidence-bar-fill" style="width: 0%; background: ${barColor};"></div>
            </div>
        `;
        container.appendChild(item);

        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                item.querySelector('.confidence-bar-fill').style.width = `${conf * 100}%`;
            });
        });
    });
}

function renderTests(tests) {
    const container = document.getElementById('tests-container');
    container.innerHTML = '';

    if (!tests || tests.length === 0) {
        container.innerHTML = '<p class="helper-text">No specific tests recommended at this time.</p>';
        return;
    }

    tests.forEach(t => {
        const priority = (t.priority || 'medium').toLowerCase();
        const icons = { high: 'exclamation', medium: 'minus', low: 'check' };

        const item = document.createElement('div');
        item.className = 'test-item';
        item.innerHTML = `
            <div class="test-icon priority-${priority}">
                <i class="fas fa-${icons[priority] || 'minus'}"></i>
            </div>
            <div class="test-info">
                <h4>${escapeHtml(t.test_name)}</h4>
                <p>${escapeHtml(t.reason)}</p>
                <div class="priority-label" style="color: var(--${priority === 'high' ? 'danger' : priority === 'low' ? 'success' : 'warning'})">${priority} priority</div>
            </div>
        `;
        container.appendChild(item);
    });
}

function renderSpecialists(specialists) {
    const container = document.getElementById('specialists-container');
    container.innerHTML = '';

    if (!specialists || specialists.length === 0) {
        container.innerHTML = '<p class="helper-text">No specific specialist referrals at this time.</p>';
        return;
    }

    specialists.forEach(s => {
        const tag = document.createElement('span');
        tag.className = 'specialist-tag';
        tag.innerHTML = `<i class="fas fa-user-md"></i> ${escapeHtml(s)}`;
        container.appendChild(tag);
    });
}

function renderAdvice(advice) {
    const container = document.getElementById('advice-container');
    container.innerHTML = `<div class="advice-box">${escapeHtml(advice)}</div>`;
}

function renderFollowUp(questions) {
    const container = document.getElementById('followup-questions-container');
    const card = document.getElementById('followup-card');
    container.innerHTML = '';

    if (!questions || questions.length === 0) {
        card.style.display = 'none';
        return;
    }

    card.style.display = 'block';
    questions.forEach((q, idx) => {
        const item = document.createElement('div');
        item.className = 'followup-item';
        item.innerHTML = `
            <label><i class="fas fa-question-circle"></i> ${escapeHtml(q)}</label>
            <textarea class="followup-answer" data-question="${escapeHtml(q)}" rows="2" placeholder="Type your answer..."></textarea>
        `;
        container.appendChild(item);
    });
}

// --- Submit Follow-up ---

async function submitFollowUp() {
    if (!currentSessionId) {
        showErrorToast('No Active Session', 'Please run a diagnosis first.');
        return;
    }

    const answerFields = document.querySelectorAll('.followup-answer');
    const answers = {};
    let hasAnswer = false;

    answerFields.forEach(field => {
        const q = field.dataset.question;
        const a = field.value.trim();
        if (a) {
            answers[q] = a;
            hasAnswer = true;
        }
    });

    if (!hasAnswer) {
        showErrorToast('Missing Answers', 'Please answer at least one follow-up question.');
        return;
    }

    const btn = document.getElementById('submit-followup-btn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Analyzing...';

    try {
        const res = await fetch(`${API_BASE}/api/followup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: currentSessionId, answers }),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
            if (res.status === 429) {
                throw { title: 'Rate Limit Reached', message: err.detail || 'The AI service is temporarily rate-limited. Please wait 1-2 minutes and try again.' };
            }
            throw { title: 'Follow-up Failed', message: err.detail || `Server error (${res.status})` };
        }

        const data = await res.json();
        renderResults({
            ...data,
            predictions: data.updated_predictions,
            follow_up_questions: data.additional_questions,
        });

        window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
        if (err.title) {
            showErrorToast(err.title, err.message, 12000);
        } else {
            showErrorToast('Connection Error', err.message || 'Could not reach the server.');
        }
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-paper-plane"></i> Submit Answers';
    }
}

// --- Reset ---

function resetForm() {
    symptoms = [];
    medicalHistory = [];
    medications = [];
    currentSessionId = null;

    document.querySelectorAll('.tags-container').forEach(c => c.innerHTML = '');
    document.querySelectorAll('input[type="text"], input[type="number"], textarea, select').forEach(el => {
        if (el.tagName === 'SELECT') el.selectedIndex = 0;
        else el.value = '';
    });

    const labContainer = document.getElementById('lab-reports-container');
    labContainer.innerHTML = `
        <div class="lab-row">
            <input type="text" class="lab-name" placeholder="e.g., HbA1c">
            <input type="text" class="lab-value" placeholder="e.g., 7.2%">
            <input type="text" class="lab-when" placeholder="e.g., Today, 2 weeks ago">
            <button type="button" class="btn-icon btn-danger" onclick="removeLabRow(this)"><i class="fas fa-times"></i></button>
        </div>
    `;

    nextStep(1);
}

// --- Print ---

function printResults() {
    window.print();
}

// ===================== CHATBOT =====================

let chatSessionId = null;
let chatOpen = false;
let chatSending = false;
let chatBubbles = []; // stored bubbles so we can toggle between home and conversation view

function toggleChat() {
    chatOpen = !chatOpen;
    const panel = document.getElementById('chat-panel');
    const toggle = document.getElementById('chat-toggle');
    const icon = document.getElementById('chat-toggle-icon');

    panel.classList.toggle('open', chatOpen);
    toggle.classList.toggle('open', chatOpen);
    icon.className = chatOpen ? 'fas fa-times' : 'fas fa-comment-medical';

    if (chatOpen) {
        const badge = document.getElementById('chat-badge');
        badge.style.display = 'none';
        setTimeout(() => document.getElementById('chat-input').focus(), 100);
    }
}

function chatGoHome() {
    const container = document.getElementById('chat-messages');
    container.innerHTML = getChatWelcomeHTML();
    updateChatHomeBtn();
}

function updateChatHomeBtn() {
    const btn = document.getElementById('chat-home-btn');
    btn.style.display = chatBubbles.length > 0 ? '' : 'none';
}

function getChatWelcomeHTML() {
    let html = `
        <div class="chat-welcome">
            <div class="chat-welcome-icon"><i class="fas fa-heartbeat"></i></div>
            <h4>Welcome to MedAgent Chat</h4>
            <p>Ask me about symptoms, diseases, medications, or general health questions. I'll use our medical knowledge base to help you.</p>
            <div class="chat-suggestions">
                <button class="chat-suggestion" onclick="sendSuggestion('What are the common symptoms of diabetes?')">Symptoms of diabetes</button>
                <button class="chat-suggestion" onclick="sendSuggestion('What causes high blood pressure?')">Causes of high BP</button>
                <button class="chat-suggestion" onclick="sendSuggestion('When should I see a doctor for a headache?')">When to see a doctor</button>
            </div>
        </div>`;
    if (chatBubbles.length > 0) {
        html += `
        <button class="chat-resume-btn" onclick="chatResumeConversation()">
            <i class="fas fa-comments"></i> Resume previous conversation (${chatBubbles.length} messages)
        </button>`;
    }
    return html;
}

function chatResumeConversation() {
    const container = document.getElementById('chat-messages');
    container.innerHTML = '';
    chatBubbles.forEach(b => container.appendChild(b.cloneNode(true)));
    container.scrollTop = container.scrollHeight;
    updateChatHomeBtn();
}

function sendSuggestion(text) {
    document.getElementById('chat-input').value = text;
    sendChatMessage();
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message || chatSending) return;

    hideWelcome();
    appendChatBubble('user', message);
    input.value = '';
    chatSending = true;
    updateSendButton(true);
    showTypingIndicator();

    try {
        const body = { message };
        if (chatSessionId) body.session_id = chatSessionId;

        const res = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        hideTypingIndicator();

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: 'Unknown error' }));
            if (res.status === 429) {
                appendChatBubble('bot', 'I\'m currently rate-limited. Please wait a minute and try again.', []);
            } else {
                appendChatBubble('bot', 'Sorry, something went wrong. Please try again.', []);
            }
            return;
        }

        const data = await res.json();
        chatSessionId = data.session_id;
        appendChatBubble('bot', data.reply, data.sources || []);
    } catch (err) {
        hideTypingIndicator();
        appendChatBubble('bot', 'Could not reach the server. Please check if the backend is running.', []);
    } finally {
        chatSending = false;
        updateSendButton(false);
    }
}

function hideWelcome() {
    const container = document.getElementById('chat-messages');
    const welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();
    const resumeBtn = container.querySelector('.chat-resume-btn');
    if (resumeBtn) resumeBtn.remove();
    // If returning from home, restore existing bubbles first
    if (chatBubbles.length > 0 && container.querySelectorAll('.chat-bubble').length === 0) {
        chatBubbles.forEach(b => container.appendChild(b.cloneNode(true)));
    }
}

function appendChatBubble(role, text, sources) {
    const container = document.getElementById('chat-messages');
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${role}`;

    if (role === 'bot') {
        bubble.innerHTML = formatBotMessage(text);
        if (sources && sources.length > 0) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.className = 'chat-sources';
            sources.forEach(s => {
                const tag = document.createElement('span');
                tag.className = 'chat-source-tag';
                tag.textContent = s;
                sourcesDiv.appendChild(tag);
            });
            bubble.appendChild(sourcesDiv);
        }
    } else {
        bubble.textContent = text;
    }

    container.appendChild(bubble);
    chatBubbles.push(bubble.cloneNode(true));
    container.scrollTop = container.scrollHeight;
    updateChatHomeBtn();
}

function formatBotMessage(text) {
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\n- /g, '\n&bull; ');
    html = html.replace(/\n\d+\.\s/g, match => '\n' + match.trim() + ' ');
    html = html.replace(/\n/g, '<br>');
    return html;
}

function showTypingIndicator() {
    const container = document.getElementById('chat-messages');
    const existing = container.querySelector('.chat-typing');
    if (existing) return;

    const typing = document.createElement('div');
    typing.className = 'chat-typing';
    typing.innerHTML = '<span></span><span></span><span></span>';
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
}

function hideTypingIndicator() {
    const typing = document.querySelector('.chat-typing');
    if (typing) typing.remove();
}

function updateSendButton(sending) {
    const btn = document.getElementById('chat-send-btn');
    btn.disabled = sending;
    btn.innerHTML = sending
        ? '<i class="fas fa-spinner fa-spin"></i>'
        : '<i class="fas fa-paper-plane"></i>';
}

function startNewChat() {
    chatSessionId = null;
    chatBubbles = [];
    const container = document.getElementById('chat-messages');
    container.innerHTML = getChatWelcomeHTML();
    updateChatHomeBtn();
}

// Chat Enter key support
document.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('keypress', e => {
            if (e.key === 'Enter') { e.preventDefault(); sendChatMessage(); }
        });
    }
});
