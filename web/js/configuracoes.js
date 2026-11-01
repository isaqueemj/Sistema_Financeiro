// Caminho: web/js/configuracoes.js
let dadosQrAtual = null;
let modoQrSelecionado = "telegram"; // 'telegram' | 'mobile'
let intervaloTimerQr = null;

document.addEventListener("DOMContentLoaded", () => {
    carregarDadosPerfil();
    configurarEventosConfiguracoes();
});

async function carregarDadosPerfil() {
    try {
        const res = await fetch(`/api/me?_t=${Date.now()}`, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store"
        });

        if (res.status === 401) {
            window.location.href = "/";
            return;
        }

        const data = await res.json();
        const user = data.usuario || data;
        if (!user || !user.email) return;

        const greeting = document.getElementById("header-user-name") || document.querySelector(".user-greeting");
        if (greeting && user.nome) {
            greeting.textContent = `Olá, ${user.nome}`;
        }

        const inputNome = document.getElementById("conf-nome") || document.querySelector("input[placeholder*='Nome']");
        const inputEmail = document.getElementById("conf-email") || document.querySelector("input[type='email']");
        const inputTgUser =
            document.getElementById("conf-telegram") ||
            document.getElementById("conf-telegram-username") ||
            document.querySelector("input[placeholder*='@']");
        const inputTgId =
            document.getElementById("conf-telegram-id") ||
            document.getElementById("conf-chat-id") ||
            document.querySelector("input[placeholder*='12345']");

        if (inputNome) inputNome.value = user.nome || "";
        if (inputEmail) inputEmail.value = user.email || "";
        if (inputTgUser) inputTgUser.value = user.telegram_username || user.telegram || "";
        if (inputTgId) inputTgId.value = user.telegram_id || user.telegram_chat_id || "";
    } catch (err) {
        console.error("Erro ao carregar perfil:", err);
    }
}

function configurarEventosConfiguracoes() {
    const formConfig = document.getElementById("form-config") || document.querySelector("form");
    if (formConfig) {
        formConfig.addEventListener("submit", salvarConfiguracoesPerfil);
    }

    const btnAbrirQr =
        document.getElementById("btn-abrir-qrcode") ||
        document.getElementById("btn-gerar-qrcode") ||
        document.querySelector(".btn-primary-qr");
    if (btnAbrirQr) {
        btnAbrirQr.addEventListener("click", (e) => {
            e.preventDefault();
            abrirModalQrCode();
        });
    }

    const btnFecharModal =
        document.getElementById("btn-fechar-modal") ||
        document.querySelector(".modal-close");
    if (btnFecharModal) {
        btnFecharModal.addEventListener("click", fecharModalQrCode);
    }

    const btnRenovar =
        document.getElementById("btn-renovar-qr") ||
        document.querySelector(".btn-link-refresh");
    if (btnRenovar) {
        btnRenovar.addEventListener("click", () => requisitarNovoQrCode());
    }

    const btnCopiar =
        document.getElementById("btn-copiar-url") ||
        document.querySelector(".btn-copy");
    if (btnCopiar) {
        btnCopiar.addEventListener("click", copiarLinkQrCode);
    }

    // Abas dentro do modal: "Abrir Bot no Telegram" vs "Chat Web Mobile"
    const abas = document.querySelectorAll(".qr-mode-tabs button, .qr-tab");
    abas.forEach((aba) => {
        aba.addEventListener("click", () => {
            abas.forEach((b) => b.classList.remove("active"));
            aba.classList.add("active");
            const txt = aba.textContent.toLowerCase();
            modoQrSelecionado = txt.includes("mobile") || txt.includes("web") ? "mobile" : "telegram";
            atualizarExibicaoQrCode();
        });
    });

    const btnLogout = document.getElementById("btn-logout");
    if (btnLogout) {
        btnLogout.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            localStorage.removeItem("usuario_logado");
            window.location.href = "/";
        });
    }
}

async function salvarConfiguracoesPerfil(e) {
    e.preventDefault();
    const inputNome = document.getElementById("conf-nome") || document.querySelector("input[placeholder*='Nome']");
    const inputTgUser =
        document.getElementById("conf-telegram") ||
        document.getElementById("conf-telegram-username") ||
        document.querySelector("input[placeholder*='@']");
    const inputTgId =
        document.getElementById("conf-telegram-id") ||
        document.getElementById("conf-chat-id") ||
        document.querySelector("input[placeholder*='12345']");
    const alertBox = document.getElementById("config-alert") || document.querySelector(".alert-box");

    const nome = (inputNome?.value || "").trim();
    const telegram_username = (inputTgUser?.value || "").trim();
    const telegram_id = (inputTgId?.value || "").trim();

    try {
        const res = await fetch("/api/usuario/configuracoes", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ nome, telegram_username, telegram_id })
        });
        const data = await res.json();

        if (alertBox) {
            alertBox.style.display = "block";
            if (res.ok && data.sucesso) {
                alertBox.className = "alert-box alert-success";
                alertBox.textContent = "Configurações atualizadas com sucesso!";
                carregarDadosPerfil();
            } else {
                alertBox.className = "alert-box alert-error";
                alertBox.textContent = data.erro || "Erro ao salvar configurações.";
            }
            setTimeout(() => { alertBox.style.display = "none"; }, 4000);
        }
    } catch (err) {
        if (alertBox) {
            alertBox.style.display = "block";
            alertBox.className = "alert-box alert-error";
            alertBox.textContent = "Erro de comunicação com o servidor.";
        }
    }
}

function abrirModalQrCode() {
    const modal = document.getElementById("modal-qrcode") || document.querySelector(".modal-overlay");
    if (modal) {
        modal.style.display = "flex";
        modal.classList.add("active");
        modal.setAttribute("aria-hidden", "false");
    }
    requisitarNovoQrCode();
}

function fecharModalQrCode() {
    const modal = document.getElementById("modal-qrcode") || document.querySelector(".modal-overlay");
    if (modal) {
        modal.style.display = "none";
        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");
    }
    if (intervaloTimerQr) clearInterval(intervaloTimerQr);
}

async function requisitarNovoQrCode() {
    const boxDisplay = document.querySelector(".qr-display-box");
    let loadingEl = document.getElementById("qr-loading") || document.querySelector(".qr-loading");
    let imgEl = document.getElementById("qr-image") || (boxDisplay ? boxDisplay.querySelector("img") : null);

    if (!imgEl && boxDisplay) {
        imgEl = document.createElement("img");
        imgEl.id = "qr-image";
        imgEl.alt = "QR Code FinanceControl";
        imgEl.style.maxWidth = "220px";
        imgEl.style.borderRadius = "8px";
        imgEl.style.display = "none";
        boxDisplay.appendChild(imgEl);
    }

    if (loadingEl) {
        loadingEl.style.display = "block";
        loadingEl.textContent = "Gerando QR Code...";
    }
    if (imgEl) imgEl.style.display = "none";

    try {
        const res = await fetch("/api/qrcode/gerar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin"
        });
        const data = await res.json();

        if (!res.ok || !data.sucesso) {
            if (loadingEl) loadingEl.textContent = data.erro || "Erro ao gerar QR Code.";
            return;
        }

        dadosQrAtual = data;
        atualizarExibicaoQrCode();
        iniciarContadorQrCode(data.validade_segundos || 600);
    } catch (err) {
        console.error("Erro ao gerar QR Code:", err);
        if (loadingEl) loadingEl.textContent = "Falha de conexão ao gerar QR Code.";
    }
}

function atualizarExibicaoQrCode() {
    if (!dadosQrAtual) return;

    const boxDisplay = document.querySelector(".qr-display-box");
    const loadingEl = document.getElementById("qr-loading") || document.querySelector(".qr-loading");
    let imgEl = document.getElementById("qr-image") || (boxDisplay ? boxDisplay.querySelector("img") : null);
    const inputUrl =
        document.getElementById("qr-url-input") ||
        document.querySelector(".qr-copy-section input");

    const imagemBase64 =
        modoQrSelecionado === "mobile"
            ? (dadosQrAtual.qr_code_mobile || dadosQrAtual.qr_code_base64)
            : (dadosQrAtual.qr_code_telegram || dadosQrAtual.qr_code_base64);

    const linkAtivo =
        modoQrSelecionado === "mobile"
            ? (dadosQrAtual.url_mobile || dadosQrAtual.link_mobile)
            : (dadosQrAtual.url_telegram || dadosQrAtual.link_telegram || dadosQrAtual.url_mobile);

    if (loadingEl) loadingEl.style.display = "none";

    if (imgEl && imagemBase64) {
        imgEl.src = imagemBase64;
        imgEl.style.display = "block";
        imgEl.style.margin = "0 auto";
    }

    if (inputUrl && linkAtivo) {
        inputUrl.value = linkAtivo;
    }
}

function iniciarContadorQrCode(segundosTotais) {
    if (intervaloTimerQr) clearInterval(intervaloTimerQr);
    let restantes = Number(segundosTotais || 600);
    const elTimer = document.getElementById("qr-countdown");

    intervaloTimerQr = setInterval(() => {
        restantes--;
        if (restantes <= 0) {
            clearInterval(intervaloTimerQr);
            if (elTimer) elTimer.textContent = "Expirado";
            return;
        }
        const min = String(Math.floor(restantes / 60)).padStart(2, "0");
        const seg = String(restantes % 60).padStart(2, "0");
        if (elTimer) elTimer.textContent = `${min}:${seg}`;
    }, 1000);
}

async function copiarLinkQrCode() {
    const inputUrl =
        document.getElementById("qr-url-input") ||
        document.querySelector(".qr-copy-section input");
    const btnCopiar =
        document.getElementById("btn-copiar-url") ||
        document.querySelector(".btn-copy");

    const texto = inputUrl ? inputUrl.value.trim() : "";
    if (!texto) return;

    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(texto);
        } else {
            inputUrl.select();
            inputUrl.setSelectionRange(0, 99999);
            document.execCommand("copy");
        }
        if (btnCopiar) {
            const original = btnCopiar.textContent;
            btnCopiar.textContent = "Copiado! ✅";
            setTimeout(() => { btnCopiar.textContent = original; }, 2000);
        }
    } catch (_) {
        inputUrl.select();
        document.execCommand("copy");
    }
}