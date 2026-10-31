// Caminho: web/js/configuracoes.js
let intervaloTimer = null;
let dadosQrAtual = null;
let modoQrSelecionado = "tg"; // "tg" (Telegram) ou "web"

document.addEventListener("DOMContentLoaded", () => {
    carregarDadosUsuario();

    const btnAbrirQr = document.getElementById("btn-abrir-qrcode");
    const btnFecharModal = document.getElementById("btn-fechar-modal");
    const modalQr = document.getElementById("modal-qrcode");
    const btnRenovarQr = document.getElementById("btn-renovar-qr");
    const btnCopiarUrl = document.getElementById("btn-copiar-url");
    const tabTg = document.getElementById("tab-qr-tg");
    const tabWeb = document.getElementById("tab-qr-web");
    const formConfig = document.getElementById("form-config");
    const btnLogout = document.getElementById("btn-logout");

    if (btnAbrirQr) {
        btnAbrirQr.addEventListener("click", () => {
            modalQr.classList.add("open");
            gerarQrCodeNoServidor();
        });
    }
    if (btnFecharModal) btnFecharModal.addEventListener("click", fecharModalQr);
    if (modalQr) {
        modalQr.addEventListener("click", (e) => {
            if (e.target === modalQr) fecharModalQr();
        });
    }
    if (btnRenovarQr) btnRenovarQr.addEventListener("click", gerarQrCodeNoServidor);
    if (tabTg && tabWeb) {
        tabTg.addEventListener("click", () => alternarModoQr("tg"));
        tabWeb.addEventListener("click", () => alternarModoQr("web"));
    }
    if (btnCopiarUrl) btnCopiarUrl.addEventListener("click", copiarLinkQrCode);
    if (formConfig) formConfig.addEventListener("submit", salvarConfiguracoesPerfil);
    if (btnLogout) {
        btnLogout.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            localStorage.removeItem("usuario_logado");
            window.location.href = "/";
        });
    }
});

async function copiarLinkQrCode() {
    const inputUrl = document.getElementById("qr-url-input");
    const btnCopiar = document.getElementById("btn-copiar-url");
    if (!inputUrl || !inputUrl.value) return;

    const textoParaCopiar = inputUrl.value.trim();
    let copiadoComSucesso = false;

    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(textoParaCopiar);
            copiadoComSucesso = true;
        }
    } catch (err) {
        copiadoComSucesso = false;
    }

    if (!copiadoComSucesso) {
        try {
            const textAreaTemp = document.createElement("textarea");
            textAreaTemp.value = textoParaCopiar;
            textAreaTemp.setAttribute("readonly", "");
            textAreaTemp.style.position = "fixed";
            textAreaTemp.style.top = "-9999px";
            document.body.appendChild(textAreaTemp);
            textAreaTemp.focus();
            textAreaTemp.select();
            copiadoComSucesso = document.execCommand("copy");
            document.body.removeChild(textAreaTemp);
        } catch (e) {
            copiadoComSucesso = false;
        }
    }

    if (copiadoComSucesso) {
        const original = btnCopiar.textContent;
        btnCopiar.textContent = "Copiado! ✅";
        btnCopiar.style.backgroundColor = "#10b981";
        setTimeout(() => {
            btnCopiar.textContent = original;
            btnCopiar.style.backgroundColor = "";
        }, 2000);
    } else {
        inputUrl.select();
    }
}

async function carregarDadosUsuario() {
    try {
        const res = await fetch("/api/auth/me");
        if (res.status === 401) {
            window.location.href = "/";
            return;
        }
        const data = await res.json();
        if (data.sucesso && data.usuario) {
            document.getElementById("header-user-name").textContent = `Olá, ${data.usuario.nome}`;
            document.getElementById("conf-nome").value = data.usuario.nome || "";
            document.getElementById("conf-email").value = data.usuario.email || "";
            document.getElementById("conf-telegram-username").value = data.usuario.telegram_username || "";
            document.getElementById("conf-telegram-chat-id").value = data.usuario.telegram_chat_id || "";
        }
    } catch (err) {
        console.error("Erro ao carregar perfil:", err);
    }
}

async function salvarConfiguracoesPerfil(e) {
    e.preventDefault();
    const nome = document.getElementById("conf-nome").value.trim();
    const telegram_username = document.getElementById("conf-telegram-username").value.trim();
    const telegram_chat_id = document.getElementById("conf-telegram-chat-id").value.trim();
    const alertBox = document.getElementById("config-alert");

    try {
        const res = await fetch("/api/usuario/configuracoes", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nome, telegram_username, telegram_chat_id })
        });
        const data = await res.json();
        alertBox.style.display = "block";
        if (res.ok && data.sucesso) {
            alertBox.className = "alert-box alert-success";
            alertBox.textContent = "Configurações do Telegram atualizadas com sucesso!";
            document.getElementById("header-user-name").textContent = `Olá, ${nome}`;
            document.getElementById("conf-telegram-username").value = data.telegram_username || "";
            document.getElementById("conf-telegram-chat-id").value = data.telegram_chat_id || "";
        } else {
            alertBox.className = "alert-box alert-error";
            alertBox.textContent = data.erro || "Erro ao salvar.";
        }
    } catch (err) {
        alertBox.style.display = "block";
        alertBox.className = "alert-box alert-error";
        alertBox.textContent = "Erro de conexão com o servidor.";
    }
}

async function gerarQrCodeNoServidor() {
    const imgQr = document.getElementById("qr-image");
    const loadingQr = document.getElementById("qr-loading");
    imgQr.style.display = "none";
    loadingQr.style.display = "block";

    try {
        const res = await fetch("/api/qrcode/gerar", { method: "POST" });
        const data = await res.json();
        if (res.ok && data.sucesso) {
            dadosQrAtual = data;
            atualizarExibicaoQr();
            iniciarContagemRegressiva(data.validade_segundos || 600);
        }
    } catch (err) {
        loadingQr.textContent = "Erro ao comunicar com o servidor.";
    }
}

function alternarModoQr(modo) {
    modoQrSelecionado = modo;
    document.getElementById("tab-qr-tg").classList.toggle("active", modo === "tg");
    document.getElementById("tab-qr-web").classList.toggle("active", modo === "web");
    if (dadosQrAtual) atualizarExibicaoQr();
}

function atualizarExibicaoQr() {
    const imgQr = document.getElementById("qr-image");
    const loadingQr = document.getElementById("qr-loading");
    const inputUrl = document.getElementById("qr-url-input");

    loadingQr.style.display = "none";
    imgQr.style.display = "block";

    if (modoQrSelecionado === "tg") {
        imgQr.src = dadosQrAtual.qr_code_telegram_base64;
        inputUrl.value = dadosQrAtual.url_telegram;
    } else {
        imgQr.src = dadosQrAtual.qr_code_web_base64;
        inputUrl.value = dadosQrAtual.url_mobile;
    }
}

function iniciarContagemRegressiva(segundosTotais) {
    if (intervaloTimer) clearInterval(intervaloTimer);
    let restante = segundosTotais;
    const elCountdown = document.getElementById("qr-countdown");

    const atualizar = () => {
        const min = String(Math.floor(restante / 60)).padStart(2, "0");
        const seg = String(restante % 60).padStart(2, "0");
        elCountdown.textContent = `${min}:${seg}`;
    };
    atualizar();
    intervaloTimer = setInterval(() => {
        restante--;
        if (restante <= 0) {
            clearInterval(intervaloTimer);
            elCountdown.textContent = "Expirado";
        } else {
            atualizar();
        }
    }, 1000);
}

function fecharModalQr() {
    document.getElementById("modal-qrcode").classList.remove("open");
    if (intervaloTimer) clearInterval(intervaloTimer);
}