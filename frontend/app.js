// Runtime config fetched from backend /client-config.
// No client IDs, tenant IDs, or scopes are hardcoded here.
const CONFIG_URL = "http://localhost:8000/client-config";

let msalInstance = null;
let apiScope = null;
let backendUrl = null;
let currentAccount = null;

async function loadConfig() {
    const resp = await fetch(CONFIG_URL);
    if (!resp.ok) {
        throw new Error(
            `Failed to load client config from ${CONFIG_URL}: ${resp.status} ${resp.statusText}`
        );
    }
    const config = await resp.json();

    const required = ["msalClientId", "authority", "redirectUri", "apiScope", "backendBaseUrl"];
    for (const key of required) {
        if (!config[key]) {
            throw new Error(`Client config missing required field: ${key}`);
        }
    }

    apiScope = config.apiScope;
    backendUrl = config.backendBaseUrl;

    const msalConfig = {
        auth: {
            clientId: config.msalClientId,
            authority: config.authority,
            redirectUri: config.redirectUri,
        },
        cache: {
            cacheLocation: "sessionStorage",
        },
    };

    msalInstance = new msal.PublicClientApplication(msalConfig);
}

async function initialize() {
    try {
        await loadConfig();
    } catch (err) {
        document.body.innerHTML =
            `<div style="padding:2rem;color:red;font-family:sans-serif">
                <strong>Configuration error:</strong> ${err.message}<br>
                Ensure the backend is running and accessible at <code>${CONFIG_URL}</code>.
            </div>`;
        return;
    }

    // Handle redirect response (if using redirect flow)
    await msalInstance.handleRedirectPromise();

    const accounts = msalInstance.getAllAccounts();
    if (accounts.length > 0) {
        currentAccount = accounts[0];
        showLoggedIn();
    }
}

async function login() {
    try {
        const response = await msalInstance.loginPopup({
            scopes: ["openid", "profile", apiScope],
        });
        currentAccount = response.account;
        showLoggedIn();
    } catch (error) {
        console.error("Login failed:", error);
        addMessage("Login failed: " + error.message, "error");
    }
}

function logout() {
    msalInstance.logoutPopup();
    currentAccount = null;
    showLoggedOut();
}

async function getAccessToken() {
    if (!currentAccount) throw new Error("Not logged in");

    try {
        const response = await msalInstance.acquireTokenSilent({
            scopes: [apiScope],
            account: currentAccount,
            forceRefresh: true,
        });
        return response.accessToken;
    } catch (error) {
        // Fall back to popup and request fresh consent when needed.
        const response = await msalInstance.acquireTokenPopup({
            scopes: [apiScope],
            prompt: "consent",
        });
        return response.accessToken;
    }
}

async function sendMessage() {
    const input = document.getElementById("message-input");
    const message = input.value.trim();
    if (!message) return;

    // Show user message
    addMessage(message, "user");
    input.value = "";

    // Show typing indicator
    const typingEl = showTyping();

    try {
        const token = await getAccessToken();
        const response = await fetch(`${backendUrl}/chat`, {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ message }),
        });

        removeTyping(typingEl);

        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: response.statusText }));
            addMessage(`Error: ${err.detail || response.statusText}`, "error");
            return;
        }

        const data = await response.json();
        addMessage(data.reply, "assistant");
    } catch (error) {
        removeTyping(typingEl);
        addMessage(`Error: ${error.message}`, "error");
    }
}

function handleKeydown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function addMessage(text, type) {
    const messagesEl = document.getElementById("messages");
    const msgEl = document.createElement("div");
    msgEl.className = `message ${type}`;
    msgEl.textContent = text;
    messagesEl.appendChild(msgEl);
    messagesEl.parentElement.scrollTop = messagesEl.parentElement.scrollHeight;
}

function showTyping() {
    const messagesEl = document.getElementById("messages");
    const el = document.createElement("div");
    el.className = "typing-indicator";
    el.textContent = "Thinking...";
    messagesEl.appendChild(el);
    messagesEl.parentElement.scrollTop = messagesEl.parentElement.scrollHeight;
    return el;
}

function removeTyping(el) {
    if (el && el.parentNode) {
        el.parentNode.removeChild(el);
    }
}

function showLoggedIn() {
    document.getElementById("login-btn").classList.add("hidden");
    document.getElementById("user-name").textContent = currentAccount.name || currentAccount.username;
    document.getElementById("user-name").classList.remove("hidden");
    document.getElementById("logout-btn").classList.remove("hidden");
    document.getElementById("input-section").classList.remove("hidden");
}

function showLoggedOut() {
    document.getElementById("login-btn").classList.remove("hidden");
    document.getElementById("user-name").classList.add("hidden");
    document.getElementById("logout-btn").classList.add("hidden");
    document.getElementById("input-section").classList.add("hidden");
}

// Initialize on load
initialize();
