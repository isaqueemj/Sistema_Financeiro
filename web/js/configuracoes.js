// Caminho: web/js/configuracoes.js
let intervaloTimer = null;
let dadosQrAtual = null;
let modoQrSelecionado = "web";

document.addEventListener("DOMContentLoaded", () => {
    carregarDadosUsuario();

    const btnAbrirQr = document.getElementById("btn-abrir-qrcode");
    const btnFecharModal = document.getElementById("btn-fechar-modal");
    const modalQr = document.getElementById("modal-qrcode");
    const btnRenovarQr = document.getElementById("btn-renovar-qr");
    const btnCopiarUrl = document.getElementById("btn-copiar-url");
    const tabWeb = document.getElementById("tab-qr-web");
    const tabWpp = document.getElementById("tab-qr-wpp");
    const formConfig = document.getElementById("form-config");
    const btnLogout = document.getElementById("btn-logout");

    if (btnAbrirQr) {
        btnAbrirQr.addEventListener("click", () => {
            modalQr.classList.add("open");
            gerarQrCodeNoServidor();
        });
    }

    if (btnFecharModal) {
        btnFecharModal.addEventListener("click", fecharModalQr);
    }

    if (modalQr) {
        modalQr.addEventListener("click", (e) => {
            if (e.target === modalQr) fecharModalQr();
        });
    }

    if (btnRenovarQr) {
        btnRenovarQr.addEventListener("click", gerarQrCodeNoServidor);
    }

    if (tabWeb && tabWpp) {
        tabWeb.addEventListener("click", () => alternarModoQr("web"));
        tabWpp.addEventListener("click", () => alternarModoQr("wpp"));
    }

    if (btnCopiarUrl) {
        btnCopiarUrl.addEventListener("click", copiarLinkQrCode);
    }

    if (formConfig) {
        formConfig.addEventListener("submit", salvarConfiguracoesPerfil);
    }

    if (btnLogout) {
        btnLogout.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            localStorage.removeItem("usuario_logado");
            window.location.href = "/";
        });
    }
});

/**
 * Função robusta de cópia que funciona tanto em HTTPS quanto em conexões HTTP locais (192.168.x.x).
 */
async function copiarLinkQrCode() {
    const inputUrl = document.getElementById("qr-url-input");
    const btnCopiar = document.getElementById("btn-copiar-url");
    if (!inputUrl || !inputUrl.value) return;

    const textoParaCopiar = inputUrl.value.trim();
    let copiadoComSucesso = false;

    try {
        // 1. Tenta usar a Clipboard API moderna se estiver em contexto seguro (HTTPS ou localhost)
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(textoParaCopiar);
            copiadoComSucesso = true;
        }
    } catch (err) {
        copiadoComSucesso = false;
    }

    // 2. Fallback com <textarea> invisível e execCommand('copy') para HTTP em rede local (192.168.x.x)
    if (!copiadoComSucesso) {
        try {
            const textAreaTemp = document.createElement("textarea");
            textAreaTemp.value = textoParaCopiar;
            textAreaTemp.setAttribute("readonly", "");
            textAreaTemp.style.position = "fixed";
            textAreaTemp.style.top = "-9999px";
            textAreaTemp.style.left = "-9999px";
            document.body.appendChild(textAreaTemp);

            textAreaTemp.focus();
            textAreaTemp.select();
            textAreaTemp.setSelectionRange(0, textoParaCopiar.length);

            copiadoComSucesso = document.execCommand("copy");
            document.body.removeChild(textAreaTemp);
        } catch (fallbackErr) {
            copiadoComSucesso = false;
        }
    }

    // 3. Feedback visual imediato ou seleção manual assistida
    if (copiadoComSucesso) {
        const textoOriginal = btnCopiar.textContent;
        btnCopiar.textContent = "Copiado! ✅";
        btnCopiar.style.backgroundColor = "#10b981";
        setTimeout(() => {
            btnCopiar.textContent = textoOriginal;
            btnCopiar.style.backgroundColor = "";
        }, 2000);
    } else {
        inputUrl.focus();
        inputUrl.select();
        alert("Link selecionado! Pressione Ctrl+C (ou segure e toque em Copiar) para copiar o endereço.");
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
            document.getElementById("conf-whatsapp").value = data.usuario.telefone_whatsapp || "";
            const elBot = document.getElementById("conf-bot-whatsapp");
            if (elBot) {
                elBot.value = data.usuario.numero_bot_efetivo || "";
            }
        }
    } catch (err) {
        console.error("Erro ao carregar perfil:", err);
    }
}

async function salvarConfiguracoesPerfil(e) {
    e.preventDefault();
    const nome = document.getElementById("conf-nome").value.trim();
    const telefone_whatsapp = document.getElementById("conf-whatsapp").value.trim();
    const elBot = document.getElementById("conf-bot-whatsapp");
    const numero_bot_whatsapp = elBot ? elBot.value.trim() : "";
    const alertBox = document.getElementById("config-alert");

    try {
        const res = await fetch("/api/usuario/configuracoes", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nome, telefone_whatsapp, numero_bot_whatsapp })
        });
        const data = await res.json();
        alertBox.style.display = "block";
        if (res.ok && data.sucesso) {
            alertBox.className = "alert-box alert-success";
            alertBox.textContent = "Configurações salvas no padrão internacional E.164!";
            document.getElementById("header-user-name").textContent = `Olá, ${nome}`;
            if (data.telefone_whatsapp) document.getElementById("conf-whatsapp").value = data.telefone_whatsapp;
            if (elBot && data.numero_bot_whatsapp) elBot.value = data.numero_bot_whatsapp;
        } else {
            alertBox.className = "alert-box alert-error";
            alertBox.textContent = data.erro || "Erro ao atualizar configurações.";
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
    loadingQr.textContent = "Gerando QR Code seguro...";

    try {
        const res = await fetch("/api/qrcode/gerar", { method: "POST" });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            dadosQrAtual = data;
            atualizarExibicaoQr();
            iniciarContagemRegressiva(data.validade_segundos || 600);
        } else {
            loadingQr.textContent = data.erro || "Erro ao gerar QR Code.";
        }
    } catch (err) {
        loadingQr.textContent = "Falha de comunicação com o servidor Flask.";
    }
}

function alternarModoQr(modo) {
    modoQrSelecionado = modo;
    document.getElementById("tab-qr-web").classList.toggle("active", modo === "web");
    document.getElementById("tab-qr-wpp").classList.toggle("active", modo === "wpp");
    if (dadosQrAtual) {
        atualizarExibicaoQr();
    }
}

function atualizarExibicaoQr() {
    const imgQr = document.getElementById("qr-image");
    const loadingQr = document.getElementById("qr-loading");
    const inputUrl = document.getElementById("qr-url-input");

    if (modoQrSelecionado === "web") {
        loadingQr.style.display = "none";
        imgQr.style.display = "block";
        imgQr.src = dadosQrAtual.qr_code_base64;
        inputUrl.value = dadosQrAtual.url_mobile;
    } else {
        if (!dadosQrAtual.url_whatsapp) {
            imgQr.style.display = "none";
            loadingQr.style.display = "block";
            loadingQr.textContent = "Configure um número de WhatsApp no padrão E.164 (+55459...) na tela de Configurações primeiro.";
            inputUrl.value = "";
            return;
        }
        loadingQr.style.display = "none";
        imgQr.style.display = "block";
        const urlEncoded = encodeURIComponent(dadosQrAtual.url_whatsapp);
        imgQr.src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${urlEncoded}`;
        inputUrl.value = dadosQrAtual.url_whatsapp;
    }
}

function iniciarContagemRegressiva(segundosTotais) {
    if (intervaloTimer) clearInterval(intervaloTimer);
    let restante = segundosTotais;
    const elCountdown = document.getElementById("qr-countdown");

    const atualizarTexto = () => {
        const min = String(Math.floor(restante / 60)).padStart(2, "0");
        const seg = String(restante % 60).padStart(2, "0");
        elCountdown.textContent = `${min}:${seg}`;
    };

    atualizarTexto();
    intervaloTimer = setInterval(() => {
        restante--;
        if (restante <= 0) {
            clearInterval(intervaloTimer);
            elCountdown.textContent = "Expirado";
            document.getElementById("qr-image").style.display = "none";
            const loadingQr = document.getElementById("qr-loading");
            loadingQr.style.display = "block";
            loadingQr.textContent = "QR Code expirado. Clique em 'Gerar novo'.";
        } else {
            atualizarTexto();
        }
    }, 1000);
}

function fecharModalQr() {
    const modalQr = document.getElementById("modal-qrcode");
    modalQr.classList.remove("open");
    if (intervaloTimer) clearInterval(intervaloTimer);
}