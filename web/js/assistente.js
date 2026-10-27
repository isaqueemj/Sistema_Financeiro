// Caminho: web/js/assistente.js
document.addEventListener("DOMContentLoaded", () => {
    carregarHistoricoConversa();

    const inputMsg = document.querySelector("input[type='text'], textarea, #chat-input");
    if (inputMsg) {
        inputMsg.addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                enviarMensagemIa();
            }
        });
    }

    const botoes = document.querySelectorAll("button");
    botoes.forEach((btn) => {
        if (btn.textContent.trim().toLowerCase() === "enviar") {
            btn.addEventListener("click", (e) => {
                e.preventDefault();
                enviarMensagemIa();
            });
        }
    });
});

function obterContainerMensagens() {
    return (
        document.getElementById("chat-messages") ||
        document.querySelector(".chat-messages") ||
        document.querySelector(".messages-container") ||
        document.querySelector("main div div")
    );
}

function adicionarBalaoMensagem(texto, remetente) {
    const container = obterContainerMensagens();
    if (!container) return;

    const msgDiv = document.createElement("div");
    msgDiv.style.maxWidth = "78%";
    msgDiv.style.padding = "12px 16px";
    msgDiv.style.borderRadius = "12px";
    msgDiv.style.marginBottom = "12px";
    msgDiv.style.lineHeight = "1.45";
    msgDiv.style.whiteSpace = "pre-wrap";

    if (remetente === "usuario") {
        msgDiv.style.marginLeft = "auto";
        msgDiv.style.backgroundColor = "#3b82f6";
        msgDiv.style.color = "#ffffff";
    } else {
        msgDiv.style.marginRight = "auto";
        msgDiv.style.backgroundColor = "#1e293b";
        msgDiv.style.color = "#f8fafc";
    }

    msgDiv.textContent = texto;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

async function carregarHistoricoConversa() {
    try {
        const res = await fetch("/api/chat/historico", { cache: "no-store" });
        if (res.status === 401) {
            window.location.href = "/";
            return;
        }
        const data = await res.json();
        if (data.sucesso && Array.isArray(data.historico) && data.historico.length > 0) {
            const container = obterContainerMensagens();
            if (container) container.innerHTML = "";
            data.historico.forEach((item) => {
                adicionarBalaoMensagem(item.mensagem, item.remetente);
            });
        }
    } catch (err) {
        console.error("Erro ao sincronizar histórico:", err);
    }
}

async function enviarMensagemIa() {
    const inputMsg = document.querySelector("input[type='text'], textarea, #chat-input");
    if (!inputMsg) return;

    const texto = inputMsg.value.trim();
    if (!texto) return;

    adicionarBalaoMensagem(texto, "usuario");
    inputMsg.value = "";

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mensagem: texto })
        });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            adicionarBalaoMensagem(data.resposta, "ia");
            // Dispara sincronização imediata com a aba de Dashboard
            if (data.transacao_registrada) {
                localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            }
        } else {
            adicionarBalaoMensagem(data.erro || "Não foi possível processar sua mensagem.", "ia");
        }
    } catch (err) {
        adicionarBalaoMensagem("Erro de conexão: Verifique se o servidor Flask está rodando.", "ia");
    }
}