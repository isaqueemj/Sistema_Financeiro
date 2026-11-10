// Caminho: web/js/configuracoes.js
let dadosQrAtual = null;
let modoQrSelecionado = "tg"; // 'tg' (Telegram) ou 'web' (Mobile Web)
let intervaloContadorQr = null;
let intervaloTimerQr = null;

document.addEventListener("DOMContentLoaded", () => {
    carregarDadosPerfil();
    inicializarPreferenciasLocais();
    configurarEventosConfiguracoes();

    // Salvar Perfil e Vínculo Telegram
    const formConfig = document.getElementById("form-config");
    if (formConfig) {
        formConfig.addEventListener("submit", salvarConfiguracoesPerfil);
    }

    // Alterar Senha (com confirmação)
    const formSenha = document.getElementById("form-alterar-senha");
    if (formSenha) {
        formSenha.addEventListener("submit", alterarSenhaUsuario);
    }

    // Testar envio no Telegram
    const btnTestarTg = document.getElementById("btn-testar-telegram");
    if (btnTestarTg) {
        btnTestarTg.addEventListener("click", enviarTesteTelegram);
    }

    // Exportar CSV e JSON
    const btnCsv = document.getElementById("btn-exportar-csv");
    if (btnCsv) btnCsv.addEventListener("click", exportarDadosCSV);

    const btnJson = document.getElementById("btn-exportar-json");
    if (btnJson) btnJson.addEventListener("click", exportarBackupJSON);

    // Manutenção de dados (limpar chat)
    const btnLimparChat = document.getElementById("btn-limpar-chat");
    if (btnLimparChat) btnLimparChat.addEventListener("click", limparHistoricoChatIA);

    // Modal QR Code
    const btnAbrirQr = document.getElementById("btn-abrir-qrcode");
    const btnFecharModal = document.getElementById("btn-fechar-modal");
    const modalQr = document.getElementById("modal-qrcode");
    const btnRenovarQr = document.getElementById("btn-renovar-qr");
    const btnCopiarUrl = document.getElementById("btn-copiar-url");
    const tabTg = document.getElementById("tab-qr-tg");
    const tabWeb = document.getElementById("tab-qr-web");

    if (btnAbrirQr) {
        btnAbrirQr.addEventListener("click", () => {
            if (modalQr) modalQr.classList.add("open");
            requisitarQrCodeDoServidor();
        });
    }

    if (btnFecharModal) {
        btnFecharModal.addEventListener("click", fecharModalQrCode);
    }

    if (modalQr) {
        modalQr.addEventListener("click", (e) => {
            if (e.target === modalQr) fecharModalQrCode();
        });
    }

    if (btnRenovarQr) {
        btnRenovarQr.addEventListener("click", () => requisitarQrCodeDoServidor());
    }

    if (btnCopiarUrl) {
        btnCopiarUrl.addEventListener("click", copiarUrlQrCode);
    }

    if (tabTg) {
        tabTg.addEventListener("click", () => alternarAbaQr("tg"));
    }
    if (tabWeb) {
        tabWeb.addEventListener("click", () => alternarAbaQr("web"));
    }

    // Logout
    const btnLogout = document.getElementById("btn-logout");
    if (btnLogout) {
        btnLogout.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            localStorage.removeItem("usuario_logado");
            window.location.href = "/";
        });
    }
});

function exibirAlertaConfig(idElemento, mensagem, tipo = "success") {
    const box = document.getElementById(idElemento);
    if (!box) return;
    box.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    box.textContent = mensagem;
    box.style.display = "block";
    setTimeout(() => {
        box.style.display = "none";
    }, 4500);
}

function inicializarPreferenciasLocais() {
    const selectLimiar = document.getElementById("select-limiar-alerta");
    if (!selectLimiar) return;

    const salvo = localStorage.getItem("limiar_alerta_teto") || "80";
    selectLimiar.value = salvo;

    selectLimiar.addEventListener("change", () => {
        localStorage.setItem("limiar_alerta_teto", selectLimiar.value);
        exibirAlertaConfig(
            "tools-alert",
            `Preferência salva: alertas preventivos configurados para ${selectLimiar.value}% do teto.`,
            "success"
        );
    });
}

// Caminho: web/js/configuracoes.js


// document.addEventListener("DOMContentLoaded", () => {
//     carregarDadosPerfil();
//     configurarEventosConfiguracoes();
// });

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
async function enviarTesteTelegram() {
    const btn = document.getElementById("btn-testar-telegram");
    const chatIdInput = (document.getElementById("conf-telegram-id")?.value || "").trim();

    if (!chatIdInput) {
        exibirAlertaConfig(
            "telegram-test-alert",
            "Informe seu Telegram Chat ID ao lado (ou envie /start para o Bot) antes de testar.",
            "error"
        );
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = "<span>⏳</span> Enviando mensagem para o seu Telegram...";
    }

    try {
        const res = await fetch("/api/configuracoes/testar-telegram", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ chat_id: chatIdInput })
        });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            exibirAlertaConfig(
                "telegram-test-alert",
                "✅ Mensagem enviada! Confira a notificação do Bot no seu Telegram.",
                "success"
            );
        } else {
            exibirAlertaConfig(
                "telegram-test-alert",
                data.erro || "Não foi possível enviar a mensagem. Verifique se o Bot está ativo.",
                "error"
            );
        }
    } catch (err) {
        exibirAlertaConfig("telegram-test-alert", "Erro de comunicação com o servidor.", "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = "<span>🔔</span> Enviar Mensagem de Teste no Meu Telegram";
        }
    }
}

async function alterarSenhaUsuario(e) {
    e.preventDefault();
    const senhaAtual = document.getElementById("senha-atual")?.value || "";
    const novaSenha = document.getElementById("nova-senha")?.value || "";
    const confirmar = document.getElementById("confirmar-nova-senha")?.value || "";

    if (novaSenha.length < 6) {
        exibirAlertaConfig("senha-alert", "A nova senha deve possuir no mínimo 6 caracteres.", "error");
        return;
    }

    if (novaSenha !== confirmar) {
        exibirAlertaConfig("senha-alert", "A confirmação de senha não confere com a nova senha digitada.", "error");
        return;
    }

    const btn = document.getElementById("btn-salvar-senha");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Atualizando...";
    }

    try {
        const res = await fetch("/api/configuracoes/alterar-senha", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    token: token,
                    senhaAtual: senhaAtual,
                    nova_senha: novaSenha,
                    confirmar_senha: confirmarSenha
                })
            });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            exibirAlertaConfig("senha-alert", "✅ Senha alterada com sucesso!", "success");
            document.getElementById("form-alterar-senha").reset();
        } else {
            exibirAlertaConfig("senha-alert", data.erro || "Senha atual incorreta ou erro ao atualizar.", "error");
        }
    } catch (err) {
        exibirAlertaConfig("senha-alert", "Erro de conexão com o servidor.", "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "🔑 Atualizar Minha Senha";
        }
    }
}

async function exportarDadosCSV() {
    try {
        const res = await fetch(`/api/dashboard/stats?periodo=todos&_t=${Date.now()}`, {
            credentials: "same-origin",
            cache: "no-store"
        });
        const data = await res.json();
        if (!data.sucesso) {
            exibirAlertaConfig("tools-alert", "Não foi possível obter os dados para exportação.", "error");
            return;
        }

        const linhas = [
            ["Origem", "Data / Dia", "Descricao", "Categoria", "Tipo", "Valor (BRL)"]
        ];

        (data.rendas_fixas || []).forEach((r) => {
            linhas.push([
                "Renda Fixa",
                `Dia ${r.day_of_month || 1}`,
                `"${(r.description || "").replace(/"/g, '""')}"`,
                "Renda Fixa Mensal",
                "Receita",
                Number(r.amount || 0).toFixed(2).replace(".", ",")
            ]);
        });

        (data.gastos_fixos || []).forEach((g) => {
            linhas.push([
                "Gasto Fixo",
                `Dia ${g.due_day || 1}`,
                `"${(g.description || "").replace(/"/g, '""')}"`,
                "Gasto Fixo Mensal",
                "Despesa",
                Number(g.amount || 0).toFixed(2).replace(".", ",")
            ]);
        });

        (data.transacoes || []).forEach((t) => {
            linhas.push([
                "Lancamento Variavel",
                t.data_transacao || "-",
                `"${(t.descricao || t.categoria || "").replace(/"/g, '""')}"`,
                `"${(t.categoria || "Outros").replace(/"/g, '""')}"`,
                t.tipo === "receita" ? "Receita" : "Despesa",
                Number(t.valor || 0).toFixed(2).replace(".", ",")
            ]);
        });

        const csvContent = "\uFEFF" + linhas.map((l) => l.join(";")).join("\r\n");
        const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = `relatorio_financecontrol_${new Date().toISOString().slice(0, 10)}.csv`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);

        exibirAlertaConfig("tools-alert", "📊 Planilha CSV gerada e baixada com sucesso!", "success");
    } catch (err) {
        exibirAlertaConfig("tools-alert", "Erro ao exportar planilha CSV.", "error");
    }
}

async function exportarBackupJSON() {
    try {
        const [resDash, resTetos] = await Promise.all([
            fetch(`/api/dashboard/stats?periodo=todos&_t=${Date.now()}`, { credentials: "same-origin" }),
            fetch(`/api/tetos?_t=${Date.now()}`, { credentials: "same-origin" })
        ]);

        const dataDash = await resDash.json();
        const dataTetos = await resTetos.json().catch(() => ({ tetos: [] }));

        const payloadBackup = {
            sistema: "FinanceControl - Assistente Financeiro IA",
            exportado_em: new Date().toISOString(),
            usuario: dataDash.usuario || {},
            resumo_atual: dataDash.resumo || {},
            rendas_fixas: dataDash.rendas_fixas || [],
            gastos_fixos: dataDash.gastos_fixos || [],
            tetos_gastos: dataTetos.tetos || [],
            transacoes: dataDash.transacoes || []
        };

        const blob = new Blob([JSON.stringify(payloadBackup, null, 2)], {
            type: "application/json;charset=utf-8;"
        });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `backup_financecontrol_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);

        exibirAlertaConfig("tools-alert", "🗂️ Backup JSON completo baixado com sucesso!", "success");
    } catch (err) {
        exibirAlertaConfig("tools-alert", "Erro ao gerar backup JSON.", "error");
    }
}

async function limparHistoricoChatIA() {
    if (!confirm("Deseja limpar o histórico de mensagens do Assistente IA? Seus lançamentos financeiros serão mantidos.")) {
        return;
    }

    try {
        const res = await fetch("/api/configuracoes/limpar-chat", {
            method: "POST",
            credentials: "same-origin"
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok && data.sucesso !== false) {
            exibirAlertaConfig("tools-alert", "🧹 Histórico de conversa da IA limpo com sucesso!", "success");
        } else {
            exibirAlertaConfig("tools-alert", data.erro || "Não foi possível limpar o histórico.", "error");
        }
    } catch (err) {
        exibirAlertaConfig("tools-alert", "Erro ao comunicar com o servidor.", "error");
    }
}

/* ==========================================================================
   Geração e Exibição do QR Code (Telegram / Mobile Web)
   ========================================================================== */
// function fecharModalQrCode() {
//     const modal = document.getElementById("modal-qrcode");
//     if (modal) modal.classList.remove("open");
//     if (intervaloContadorQr) clearInterval(intervaloContadorQr);
// }

// async function requisitarQrCodeDoServidor() {
//     const loading = document.getElementById("qr-loading");
//     const img = document.getElementById("qr-image");
//     if (loading) loading.style.display = "block";
//     if (img) img.style.display = "none";

//     try {
//         const res = await fetch(`/api/qrcode/gerar?_t=${Date.now()}`, {
//             method: "POST",
//             credentials: "same-origin"
//         });
//         const data = await res.json();
//         if (res.ok && data.sucesso) {
//             dadosQrAtual = data;
//             atualizarExibicaoQrCode();
//             iniciarContagemRegressivaQr(data.expira_em_segundos || 600);
//         } else {
//             if (loading) loading.textContent = data.erro || "Erro ao gerar QR Code.";
//         }
//     } catch (err) {
//         if (loading) loading.textContent = "Erro ao conectar com o servidor.";
//     }
// }

function alternarAbaQr(modo) {
    modoQrSelecionado = modo;
    document.getElementById("tab-qr-tg")?.classList.toggle("active", modo === "tg");
    document.getElementById("tab-qr-web")?.classList.toggle("active", modo === "web");
    atualizarExibicaoQrCode();
}



function iniciarContagemRegressivaQr(segundosTotais) {
    if (intervaloContadorQr) clearInterval(intervaloContadorQr);
    let restante = segundosTotais;
    const elTimer = document.getElementById("qr-countdown");

    intervaloContadorQr = setInterval(() => {
        restante--;
        if (restante <= 0) {
            clearInterval(intervaloContadorQr);
            if (elTimer) elTimer.textContent = "Expirado";
            return;
        }
        const m = String(Math.floor(restante / 60)).padStart(2, "0");
        const s = String(restante % 60).padStart(2, "0");
        if (elTimer) elTimer.textContent = `${m}:${s}`;
    }, 1000);
}

async function copiarUrlQrCode() {
    const inputUrl = document.getElementById("qr-url-input");
    const btn = document.getElementById("btn-copiar-url");
    const texto = inputUrl?.value || "";
    if (!texto) return;

    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(texto);
        } else {
            inputUrl.select();
            inputUrl.setSelectionRange(0, 99999);
            document.execCommand("copy");
        }
        if (btn) {
            const original = btn.textContent;
            btn.textContent = "Copiado! ✅";
            setTimeout(() => (btn.textContent = original), 2000);
        }
    } catch (_) {
        inputUrl.select();
        document.execCommand("copy");
    }
}