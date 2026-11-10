// Caminho: web/js/configuracoes.js

let intervaloTimerQR = null;
let tempoRestanteQR = 60;
let modoAtualQR = "telegram";

// Deixe true para ocultar o botão de testar o bot na tela, ou false se quiser exibi-lo
const OCULTAR_BOTAO_TESTE_TELEGRAM = true;

// Utilitário para buscar um elemento por múltiplos IDs ou seletor CSS
function obterElemento(...seletores) {
    for (const sel of seletores) {
        if (!sel) continue;
        const porId = document.getElementById(sel);
        if (porId) return porId;
        try {
            const porQuery = document.querySelector(sel);
            if (porQuery) return porQuery;
        } catch (_) {}
    }
    return null;
}

// Exibe alertas visuais no card específico
function mostrarAlertaCard(idAlertaPreferencial, elementoReferencia, mensagem, tipo = "success") {
    let box = obterElemento(idAlertaPreferencial);

    if (!box && elementoReferencia) {
        const card = elementoReferencia.closest(".settings-card");
        if (card) {
            box = card.querySelector(".alert-box");
            if (!box) {
                box = document.createElement("div");
                box.className = "alert-box";
                const desc = card.querySelector(".card-desc") || card.querySelector("h2");
                if (desc && desc.parentNode) {
                    desc.insertAdjacentElement("afterend", box);
                } else {
                    card.prepend(box);
                }
            }
        }
    }

    if (!box) {
        box = obterElemento("config-alert", "alert-config", ".alert-box");
    }

    if (!box) return;

    box.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    box.textContent = mensagem;
    box.style.display = "block";

    clearTimeout(box._timeoutId);
    box._timeoutId = setTimeout(() => {
        box.style.display = "none";
    }, 5000);
}

document.addEventListener("DOMContentLoaded", () => {
    // 1. Carrega dados do perfil e configurações existentes (Mantido intacto)
    carregarDadosConfiguracoes();
    carregarDadosPerfil();

    // 2. Formulário de Perfil e Vínculo Telegram (Card 2)
    const formPerfil = obterElemento("form-configuracoes", "form-perfil", "form-perfil-telegram");
    if (formPerfil) {
        formPerfil.addEventListener("submit", salvarConfiguracoesPerfil);
    }

    // 3. Modal e Geração de QR Code (Card 1 - Mantido intacto)
    const btnAbrirQR = obterElemento("btn-gerar-qr", "btn-abrir-qrcode", ".btn-primary-qr");
    if (btnAbrirQR) {
        btnAbrirQR.addEventListener("click", () => abrirModalQRCode("telegram"));
    }

    const btnFecharQR = obterElemento("btn-fechar-modal", "close-modal-qr", ".modal-close");
    if (btnFecharQR) {
        btnFecharQR.addEventListener("click", fecharModalQRCode);
    }

    const modalOverlay = obterElemento("modal-qrcode", ".modal-overlay");
    if (modalOverlay) {
        modalOverlay.addEventListener("click", (e) => {
            if (e.target === modalOverlay) fecharModalQRCode();
        });
    }

    const abasQR = document.querySelectorAll(".qr-tab");
    abasQR.forEach((aba) => {
        aba.addEventListener("click", () => {
            abasQR.forEach((t) => t.classList.remove("active"));
            aba.classList.add("active");
            const modo = aba.dataset.mode || aba.dataset.modo || (aba.textContent.toLowerCase().includes("web") ? "web" : "telegram");
            modoAtualQR = modo;
            gerarQRCodeDinamico(modo);
        });
    });

    const btnRefreshQR = obterElemento("btn-refresh-qr", ".btn-link-refresh");
    if (btnRefreshQR) {
        btnRefreshQR.addEventListener("click", () => gerarQRCodeDinamico(modoAtualQR));
    }

    const btnCopiarLink = obterElemento("btn-copiar-link", ".btn-copy");
    if (btnCopiarLink) {
        btnCopiarLink.addEventListener("click", copiarLinkQRCode);
    }

    // 4. Botão de Teste do Telegram (Ocultado por padrão conforme solicitado)
    const btnTestarTelegram = obterElemento("btn-testar-telegram", "btn-teste-telegram", ".qr-actions-stack .btn-secondary-action");
    if (btnTestarTelegram) {
        if (OCULTAR_BOTAO_TESTE_TELEGRAM) {
            btnTestarTelegram.style.display = "none";
        } else {
            btnTestarTelegram.addEventListener("click", dispararMensagemTesteTelegram);
        }
    }

    // 5. Formulário de Alterar Senha de Acesso (Card 3)
    let formSenha = obterElemento("form-alterar-senha", "form-senha", "form-trocar-senha");
    if (!formSenha) {
        const inputPass = document.querySelector(".settings-card input[type='password']");
        if (inputPass) formSenha = inputPass.closest("form");
    }
    if (formSenha) {
        formSenha.addEventListener("submit", processarAlteracaoSenha);
    }

    // 6. Seletor de Alerta Preventivo de Teto de Gastos (Card 4)
    const selectAlertaTeto = obterElemento("select-alerta-teto", "pref-alerta-teto", ".select-pref");
    if (selectAlertaTeto) {
        const valorSalvo = localStorage.getItem("alerta_teto_percentual") || localStorage.getItem("pref_alerta_teto") || "80";
        if (["50", "70", "80", "90", "100"].includes(String(valorSalvo))) {
            selectAlertaTeto.value = String(valorSalvo);
        }

        selectAlertaTeto.addEventListener("change", async (e) => {
            await atualizarGatilhoAlertaTeto(e.target.value, selectAlertaTeto);
        });
    }

    // 7. Botões de Exportação e Manutenção (Card 4)
    const btnExportCSV = obterElemento("btn-export-csv", "btn-exportar-csv");
    if (btnExportCSV) {
        btnExportCSV.addEventListener("click", () => exportarRelatorioFinanceiro("csv", btnExportCSV));
    }

    const btnExportJSON = obterElemento("btn-export-json", "btn-exportar-json");
    if (btnExportJSON) {
        btnExportJSON.addEventListener("click", () => exportarRelatorioFinanceiro("json", btnExportJSON));
    }

    const btnLimparChat = obterElemento("btn-limpar-chat", ".btn-tool-danger-outline");
    if (btnLimparChat) {
        btnLimparChat.addEventListener("click", limparHistoricoChat);
    }

    const btnZerarTransacoes = obterElemento("btn-zerar-transacoes", ".btn-tool-danger");
    if (btnZerarTransacoes) {
        btnZerarTransacoes.addEventListener("click", zerarTransacoesVariaveis);
    }

    // 8. Logout
    const btnLogout = obterElemento("btn-logout", ".btn-logout");
    if (btnLogout) {
        btnLogout.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
            localStorage.removeItem("usuario_logado");
            window.location.href = "/";
        });
    }
});

// =========================================================================
// CARREGAMENTO E SALVAMENTO DE DADOS DO PERFIL (TABELA `usuarios`)
// =========================================================================
function obterInputsPerfil() {
    const inputNome = obterElemento(
        "conf-nome", "input-nome", "nome", "config-nome", "input[placeholder*='Nome']"
    );
    const inputEmail = obterElemento(
        "conf-email", "input-email", "email", "config-email", "input[type='email']"
    );
    const inputUsername = obterElemento(
        "conf-telegram", "conf-telegram-username", "input-telegram",
        "telegram-username", "input-username", "telegram_username", "input[placeholder*='@']"
    );
    const inputChatId = obterElemento(
        "conf-telegram-id", "conf-chat-id", "input-chat-id",
        "telegram-chat-id", "chat-id", "telegram_id", "telegram_chat_id", "input[placeholder*='12345']"
    );
    return { inputNome, inputEmail, inputUsername, inputChatId };
}

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

        const { inputNome, inputEmail, inputUsername, inputChatId } = obterInputsPerfil();

        if (inputNome) inputNome.value = user.nome || "";
        if (inputEmail) inputEmail.value = user.email || "";
        if (inputUsername) inputUsername.value = user.telegram_username || user.telegram || "";
        if (inputChatId) inputChatId.value = user.telegram_id || user.telegram_chat_id || "";
    } catch (err) {
        console.error("Erro ao carregar perfil:", err);
    }
}

async function carregarDadosConfiguracoes() {
    try {
        let res = await fetch(`/api/configuracoes?_t=${Date.now()}`, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store"
        });

        if (res.status === 404) {
            res = await fetch(`/api/auth/perfil?_t=${Date.now()}`, {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store"
            });
        }

        if (res.status === 401) {
            window.location.href = "/";
            return;
        }

        const data = await res.json();
        const user = data.usuario || data.perfil || data || {};

        const nomeUsuario = user.nome || "";
        const emailUsuario = user.email || "";
        const telegramUser = user.telegram_username || user.telegram || "";
        const telegramChatId = user.telegram_id || user.telegram_chat_id || "";
        const alertaTeto = user.alerta_teto || localStorage.getItem("alerta_teto_percentual") || "80";

        const elGreeting = obterElemento("header-user-name", "user-name", "config-user-name", ".user-greeting");
        if (elGreeting && nomeUsuario) {
            elGreeting.textContent = `Olá, ${nomeUsuario}`;
        }

        const { inputNome, inputEmail, inputUsername, inputChatId } = obterInputsPerfil();
        if (inputNome && nomeUsuario) inputNome.value = nomeUsuario;
        if (inputEmail && emailUsuario) inputEmail.value = emailUsuario;
        if (inputUsername && telegramUser) inputUsername.value = telegramUser;
        if (inputChatId && telegramChatId) inputChatId.value = telegramChatId;

        const selectAlertaTeto = obterElemento("select-alerta-teto", "pref-alerta-teto", ".select-pref");
        if (selectAlertaTeto && alertaTeto) {
            selectAlertaTeto.value = String(alertaTeto);
            localStorage.setItem("alerta_teto_percentual", String(alertaTeto));
            localStorage.setItem("pref_alerta_teto", String(alertaTeto));
        }
    } catch (err) {
        console.error("Erro ao carregar configurações:", err);
    }
}

async function salvarConfiguracoesPerfil(e) {
    e.preventDefault();
    const { inputNome, inputUsername, inputChatId } = obterInputsPerfil();

    const nome = inputNome ? inputNome.value.trim() : "";
    let telegram_username = inputUsername ? inputUsername.value.trim() : "";
    const telegram_id = inputChatId ? inputChatId.value.trim() : "";

    if (telegram_username && !telegram_username.startsWith("@") && !telegram_username.startsWith("+")) {
        telegram_username = "@" + telegram_username;
        if (inputUsername) inputUsername.value = telegram_username;
    }

    const btnSubmit = e.target.querySelector("button[type='submit']") || obterElemento(".btn-save");
    const textoOriginal = btnSubmit ? btnSubmit.textContent : "Salvar Configurações";
    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = "⏳ Salvando...";
    }

    try {
        // Envia exatamente os nomes das colunas da tabela `usuarios`
        const payload = {
            nome,
            telegram_username,
            telegram_id,
            telegram_chat_id: telegram_id
        };

        let res = await fetch("/api/configuracoes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify(payload)
        });

        if (res.status === 404 || res.status === 405) {
            res = await fetch("/api/auth/perfil", {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify(payload)
            });
        }

        const data = await res.json();
        if (res.ok && data.sucesso !== false) {
            const elGreeting = obterElemento("header-user-name", "user-name", "config-user-name", ".user-greeting");
            if (elGreeting && nome) elGreeting.textContent = `Olá, ${nome}`;
            mostrarAlertaCard("config-alert", e.target, "Configurações e vínculo salvos com sucesso!", "success");
        } else {
            mostrarAlertaCard("config-alert", e.target, data.erro || "Erro ao salvar configurações.", "error");
        }
    } catch (err) {
        mostrarAlertaCard("config-alert", e.target, "Erro de conexão com o servidor.", "error");
    } finally {
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.textContent = textoOriginal;
        }
    }
}

// =========================================================================
// ALTERAÇÃO DE SENHA DE ACESSO (ATUALIZA `senha_hash` NA TABELA `usuarios`)
// =========================================================================
async function processarAlteracaoSenha(e) {
    e.preventDefault();
    const form = e.target;

    const inputsPassword = form.querySelectorAll("input[type='password']");
    const elSenhaAtual = obterElemento("senha-atual", "input-senha-atual", "conf-senha-atual") || inputsPassword[0];
    const elNovaSenha = obterElemento("nova-senha", "input-nova-senha", "conf-nova-senha") || inputsPassword[1];
    const elConfirmarSenha = obterElemento("confirmar-senha", "input-confirmar-senha", "confirmar-nova-senha", "conf-confirmar-senha") || inputsPassword[2];

    const senha_atual = elSenhaAtual ? elSenhaAtual.value : "";
    const nova_senha = elNovaSenha ? elNovaSenha.value : "";
    const confirmar_senha = elConfirmarSenha ? elConfirmarSenha.value : "";

    if (!senha_atual) {
        mostrarAlertaCard("senha-alert", form, "Digite sua senha atual para continuar.", "error");
        if (elSenhaAtual) elSenhaAtual.focus();
        return;
    }

    if (!nova_senha || nova_senha.length < 6) {
        mostrarAlertaCard("senha-alert", form, "A nova senha deve ter no mínimo 6 dígitos.", "error");
        if (elNovaSenha) elNovaSenha.focus();
        return;
    }

    if (nova_senha !== confirmar_senha) {
        mostrarAlertaCard("senha-alert", form, "A confirmação de senha não coincide com a nova senha.", "error");
        if (elConfirmarSenha) elConfirmarSenha.focus();
        return;
    }

    const btnSubmit = form.querySelector("button[type='submit']") || form.querySelector("button");
    const textoOriginal = btnSubmit ? btnSubmit.innerHTML : "🔑 Atualizar Minha Senha";
    if (btnSubmit) {
        btnSubmit.disabled = true;
        btnSubmit.textContent = "⏳ Atualizando senha...";
    }

    try {
        const res = await fetch("/api/configuracoes/alterar-senha", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                senha_atual,
                nova_senha,
                confirmar_senha
            })
        });

        const data = await res.json();

        if (res.ok && data.sucesso) {
            mostrarAlertaCard("senha-alert", form, data.mensagem || "Senha atualizada com sucesso na tabela usuarios! 🔒", "success");
            form.reset();
        } else {
            mostrarAlertaCard("senha-alert", form, data.erro || "Não foi possível alterar a senha. Verifique sua senha atual.", "error");
        }
    } catch (err) {
        mostrarAlertaCard("senha-alert", form, "Erro de comunicação com o servidor ao alterar a senha.", "error");
    } finally {
        if (btnSubmit) {
            btnSubmit.disabled = false;
            btnSubmit.innerHTML = textoOriginal;
        }
    }
}

// =========================================================================
// ENVIAR MENSAGEM DE TESTE NO TELEGRAM (CASO EXIBIDO)
// =========================================================================
async function dispararMensagemTesteTelegram() {
    const btn = obterElemento("btn-testar-telegram", "btn-teste-telegram", ".qr-actions-stack .btn-secondary-action");
    const { inputChatId } = obterInputsPerfil();
    const chatId = inputChatId ? inputChatId.value.trim() : "";

    const htmlOriginal = btn ? btn.innerHTML : "🔔 Enviar Mensagem de Teste no Meu Telegram";
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = "⏳ Enviando mensagem para o Bot...";
    }

    try {
        const res = await fetch("/api/configuracoes/testar-telegram", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                chat_id: chatId,
                telegram_id: chatId
            })
        });

        const data = await res.json();

        if (res.ok && data.sucesso) {
            mostrarAlertaCard("telegram-alert", btn, data.mensagem || "✅ Mensagem de teste enviada com sucesso!", "success");
        } else {
            mostrarAlertaCard("telegram-alert", btn, data.erro || "Falha ao enviar mensagem de teste.", "error");
        }
    } catch (err) {
        mostrarAlertaCard("telegram-alert", btn, "Erro de conexão ao tentar enviar mensagem de teste.", "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = htmlOriginal;
        }
    }
}

// =========================================================================
// ALERTA PREVENTIVO DE TETO DE GASTOS FUNCIONAL (CARD 4)
// =========================================================================
async function atualizarGatilhoAlertaTeto(novoPercentual, selectEl) {
    const limite = Number(novoPercentual) || 80;

    localStorage.setItem("alerta_teto_percentual", String(limite));
    localStorage.setItem("pref_alerta_teto", String(limite));
    localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());

    const { inputChatId } = obterInputsPerfil();
    const chatId = inputChatId ? inputChatId.value.trim() : "";

    try {
        const res = await fetch("/api/configuracoes/alerta-teto", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                percentual: limite,
                chat_id: chatId
            })
        });

        if (res.ok) {
            const data = await res.json();
            if (data.alertas_ativos && data.alertas_ativos.length > 0) {
                const listaCategorias = data.alertas_ativos
                    .map((a) => `${a.categoria} (${Number(a.percentual).toFixed(0)}%)`)
                    .join(", ");
                mostrarAlertaCard(
                    "tools-alert",
                    selectEl,
                    `⚠️ Gatilho ajustado para ${limite}%! Atenção: ${listaCategorias} já atingiu este limite.`,
                    "error"
                );
                return;
            }
        }

        mostrarAlertaCard(
            "tools-alert",
            selectEl,
            `✅ Alerta preventivo configurado para ${limite}% do teto!`,
            "success"
        );
    } catch (err) {
        mostrarAlertaCard(
            "tools-alert",
            selectEl,
            `✅ Alerta preventivo atualizado para ${limite}% do teto!`,
            "success"
        );
    }
}

// =========================================================================
// GERADOR E MODAL DE QR CODE DINÂMICO (MANTIDO INTACTO)
// =========================================================================
function abrirModalQRCode(modo = "telegram") {
    const modal = obterElemento("modal-qrcode", ".modal-overlay");
    if (!modal) return;
    modal.classList.add("open");
    modoAtualQR = modo;
    gerarQRCodeDinamico(modo);
}

function fecharModalQRCode() {
    const modal = obterElemento("modal-qrcode", ".modal-overlay");
    if (modal) modal.classList.remove("open");
    if (intervaloTimerQR) {
        clearInterval(intervaloTimerQR);
        intervaloTimerQR = null;
    }
}

async function gerarQRCodeDinamico(modo = "telegram") {
    const imgQR = obterElemento("qr-image", "img-qrcode", ".qr-display-box img");
    const loadingQR = obterElemento("qr-loading", ".qr-loading");
    const inputLink = obterElemento("qr-link-input", "input-link-qr", ".qr-copy-section input");

    if (loadingQR) {
        loadingQR.style.display = "block";
        loadingQR.textContent = "Gerando QR Code seguro...";
    }
    if (imgQR) imgQR.style.display = "none";

    try {
        let res = await fetch(`/api/configuracoes/qrcode?modo=${encodeURIComponent(modo)}&_t=${Date.now()}`, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store"
        });

        if (res.status === 404) {
            res = await fetch(`/api/qrcode?modo=${encodeURIComponent(modo)}&_t=${Date.now()}`, {
                method: "GET",
                credentials: "same-origin",
                cache: "no-store"
            });
        }

        const data = await res.json();
        const link = data.link || data.url || window.location.origin;
        const qrBase64 = data.qr_base64 || data.qr_code || data.imagem || "";

        if (inputLink) inputLink.value = link;

        if (imgQR) {
            if (qrBase64) {
                imgQR.src = qrBase64.startsWith("data:image") ? qrBase64 : `data:image/png;base64,${qrBase64}`;
            } else {
                imgQR.src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(link)}`;
            }
            imgQR.onload = () => {
                if (loadingQR) loadingQR.style.display = "none";
                imgQR.style.display = "block";
            };
        }

        iniciarContadorQRCode(data.expira_em || 60);
    } catch (err) {
        const linkFallback = `${window.location.origin}/pages/assistente.html`;
        if (inputLink) inputLink.value = linkFallback;
        if (imgQR) {
            imgQR.src = `https://api.qrserver.com/v1/create-qr-code/?size=220x220&data=${encodeURIComponent(linkFallback)}`;
            imgQR.style.display = "block";
        }
        if (loadingQR) loadingQR.style.display = "none";
    }
}

function iniciarContadorQRCode(segundos = 60) {
    if (intervaloTimerQR) clearInterval(intervaloTimerQR);
    tempoRestanteQR = segundos;
    const elTimer = obterElemento("qr-timer", "timer-qrcode", ".qr-timer-bar span");

    const atualizarTexto = () => {
        if (elTimer) elTimer.textContent = `⏳ Expira em ${tempoRestanteQR}s`;
    };
    atualizarTexto();

    intervaloTimerQR = setInterval(() => {
        tempoRestanteQR -= 1;
        if (tempoRestanteQR <= 0) {
            clearInterval(intervaloTimerQR);
            gerarQRCodeDinamico(modoAtualQR);
        } else {
            atualizarTexto();
        }
    }, 1000);
}

function copiarLinkQRCode() {
    const inputLink = obterElemento("qr-link-input", "input-link-qr", ".qr-copy-section input");
    const btnCopy = obterElemento("btn-copiar-link", ".btn-copy");
    if (!inputLink || !inputLink.value) return;

    const confirmarCopia = () => {
        if (!btnCopy) return;
        const original = btnCopy.textContent;
        btnCopy.textContent = "Copiado! ✅";
        setTimeout(() => {
            btnCopy.textContent = original;
        }, 2000);
    };

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(inputLink.value).then(confirmarCopia);
    } else {
        inputLink.select();
        inputLink.setSelectionRange(0, 99999);
        document.execCommand("copy");
        confirmarCopia();
    }
}

// =========================================================================
// EXPORTAÇÃO DE RELATÓRIOS E MANUTENÇÃO (CARD 4)
// =========================================================================
async function exportarRelatorioFinanceiro(formato, btnRef) {
    try {
        const res = await fetch("/api/dashboard/stats?periodo=todos", { credentials: "same-origin" });
        const data = await res.json();
        const transacoes = data.transacoes || data.ultimas_transacoes || [];

        if (formato === "json") {
            const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8;" });
            baixarArquivoBlob(blob, `backup_financecontrol_${Date.now()}.json`);
        } else {
            const cabecalho = "ID;Data;Tipo;Categoria;Descricao;Valor\n";
            const linhas = transacoes.map((t) =>
                `${t.id || ""};${t.data || ""};${t.tipo || ""};"${(t.categoria || "").replace(/"/g, '""')}";"${(t.descricao || "").replace(/"/g, '""')}";${Number(t.valor || 0).toFixed(2).replace(".", ",")}`
            ).join("\n");
            const blob = new Blob(["\uFEFF" + cabecalho + linhas], { type: "text/csv;charset=utf-8;" });
            baixarArquivoBlob(blob, `relatorio_financecontrol_${Date.now()}.csv`);
        }
        mostrarAlertaCard("tools-alert", btnRef, `Arquivo .${formato.toUpperCase()} exportado com sucesso!`, "success");
    } catch (err) {
        mostrarAlertaCard("tools-alert", btnRef, "Erro ao exportar os dados financeiros.", "error");
    }
}

function baixarArquivoBlob(blob, nomeArquivo) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nomeArquivo;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

async function limparHistoricoChat(e) {
    const btn = e.currentTarget;
    if (!confirm("Deseja realmente limpar o histórico de conversas do Assistente IA?")) return;
    try {
        const res = await fetch("/api/configuracoes/limpar-chat", { method: "POST", credentials: "same-origin" });
        if (res.ok) {
            mostrarAlertaCard("tools-alert", btn, "Histórico do chat limpo com sucesso!", "success");
        }
    } catch (_) {
        mostrarAlertaCard("tools-alert", btn, "Erro ao limpar histórico do chat.", "error");
    }
}

async function zerarTransacoesVariaveis(e) {
    const btn = e.currentTarget;
    if (!confirm("ATENÇÃO: Deseja apagar todas as transações variáveis? Esta ação não pode ser desfeita.")) return;
    try {
        const res = await fetch("/api/configuracoes/zerar-transacoes", { method: "POST", credentials: "same-origin" });
        if (res.ok) {
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            mostrarAlertaCard("tools-alert", btn, "Transações variáveis removidas com sucesso!", "success");
        }
    } catch (_) {
        mostrarAlertaCard("tools-alert", btn, "Erro ao zerar transações.", "error");
    }
}