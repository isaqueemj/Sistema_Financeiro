// Caminho: web/js/assistente.js
let mapaTransacoesPorId = {};
let listaTransacoesCache = [];

function formatarMoeda(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatarMarkdownParaHTML(texto) {
    if (!texto) return "";
    return texto
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\*([^*]+)\*/g, "<strong>$1</strong>")
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\n/g, "<br>");
}

document.addEventListener("DOMContentLoaded", () => {
    carregarDadosUsuarioESaldo();

    const chatForm = document.getElementById("chat-form");
    if (chatForm) {
        chatForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const input = document.getElementById("chat-input");
            const msg = input.value.trim();
            if (!msg) return;
            input.value = "";
            await enviarMensagemAoBot(msg);
        });
    }

    const btnLogout = document.getElementById("btn-logout");
    if (btnLogout) {
        btnLogout.addEventListener("click", async () => {
            await fetch("/api/auth/logout", { method: "POST" });
            localStorage.removeItem("usuario_logado");
            window.location.href = "/";
        });
    }
});

function preencherInput(texto) {
    const input = document.getElementById("chat-input");
    if (input) {
        input.value = texto;
        input.focus();
    }
}

function enviarComandoRapido(comando) {
    enviarMensagemAoBot(comando);
}

function adicionarBalaoMensagem(remetente, textoHTML, graficos = null) {
    const container = document.getElementById("chat-messages");
    const row = document.createElement("div");
    row.className = `msg-row ${remetente}`;

    const hora = new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    const avatar = remetente === "user" ? "👤" : "🤖";

    const idGraficoUnico = `chat-chart-${Date.now()}`;
    let htmlGraficos = "";
    if (graficos) {
        htmlGraficos = `
            <div class="chat-charts-box">
                <div class="chat-chart-item"><canvas id="${idGraficoUnico}-pizza"></canvas></div>
                <div class="chat-chart-item"><canvas id="${idGraficoUnico}-barras"></canvas></div>
                <div class="chat-chart-item"><canvas id="${idGraficoUnico}-linha"></canvas></div>
            </div>
        `;
    }

    row.innerHTML = `
        <div class="msg-avatar">${avatar}</div>
        <div class="msg-bubble">
            <div>${textoHTML}</div>
            ${htmlGraficos}
            <span class="msg-time">${hora}</span>
        </div>
    `;

    container.appendChild(row);
    container.scrollTop = container.scrollHeight;

    if (graficos) {
        // Um pequeno delay para garantir que o DOM renderizou o Canvas antes de instanciar o Chart.js
        setTimeout(() => {
            renderizarGraficosNoBalao(idGraficoUnico, graficos);
        }, 50);
    }
}

// Caminho: web/js/assistente.js (Substitua as funções resolverDadosEvolucaoComNomes, renderizarGraficosNoBalao e enviarMensagemAoBot)

function resolverDadosEvolucaoComNomes(evolucao) {
    const labelsOriginais = evolucao?.labels || ["Hoje"];
    const saldos = (evolucao?.saldos || [0]).map(Number);
    const transacoesOrdenadas = [...listaTransacoesCache].sort((a, b) => Number(a.id || 0) - Number(b.id || 0));

    const labelsNomes = [];
    const detalhesTooltip = [];
    const coresPontos = [];

    labelsOriginais.forEach((lbl, idx) => {
        const strLbl = String(lbl).trim();
        const matchId = strLbl.match(/^#?(\d+)$/);

        let transacao = null;
        if (matchId) {
            transacao = mapaTransacoesPorId[matchId[1]] || mapaTransacoesPorId[`#${matchId[1]}`];
        }
        if (!transacao && idx > 0 && transacoesOrdenadas[idx - 1] && strLbl.startsWith("#")) {
            transacao = transacoesOrdenadas[idx - 1];
        }

        if (transacao) {
            const nomeGasto = (transacao.descricao || transacao.categoria || strLbl).trim();
            const categoria = (transacao.categoria || "Outros").trim();
            const valor = Number(transacao.valor || 0);
            const ehReceita = transacao.tipo === "receita";

            const nomeCurto = nomeGasto.length > 14 ? nomeGasto.slice(0, 12) + "…" : nomeGasto;
            labelsNomes.push(nomeCurto);

            detalhesTooltip.push({
                titulo: `${ehReceita ? "💰" : "💸"} ${nomeGasto} (${categoria})`,
                movimento: `${ehReceita ? "Entrada: +" : "Gasto: -"}${formatarMoeda(valor)}`
            });
            coresPontos.push(ehReceita ? "#10b981" : "#ef4444");
        } else {
            labelsNomes.push(strLbl);
            const variacao = idx > 0 ? saldos[idx] - saldos[idx - 1] : 0;
            detalhesTooltip.push({
                titulo: `📌 ${strLbl}`,
                movimento: idx > 0 && variacao !== 0
                    ? `${variacao > 0 ? "Entrada: +" : "Gasto: -"}${formatarMoeda(Math.abs(variacao))}`
                    : "Saldo base inicial (Fixos)"
            });
            coresPontos.push("#3b82f6");
        }
    });

    return { labelsNomes, saldos, detalhesTooltip, coresPontos };
}

function renderizarGraficosNoBalao(prefixoId, graficos) {
    if (!graficos || typeof Chart === "undefined") return;

    // Busca pela nomenclatura antiga (.pizza) ou pela nova usada no obter_resumo_financeiro (.grafico_pizza)
    const dPizza = graficos.grafico_pizza || graficos.pizza || {};
    const dColunas = graficos.grafico_colunas || graficos.colunas || graficos.barras || {};
    const dEvolucao = graficos.grafico_evolucao || graficos.evolucao || {};

    // 1. Gráfico de Pizza
    const ctxPizza = document.getElementById(`${prefixoId}-pizza`);
    if (ctxPizza) {
        new Chart(ctxPizza, {
            type: "doughnut",
            data: {
                labels: dPizza.labels?.length ? dPizza.labels : ["Sem gastos"],
                datasets: [{
                    data: dPizza.valores?.length ? dPizza.valores : [1],
                    backgroundColor: ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899"]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: "#f8fafc", font: { size: 10 } } },
                    tooltip: {
                        callbacks: {
                            label: (ctx) => ` ${ctx.label}: ${formatarMoeda(ctx.parsed)}`
                        }
                    }
                }
            }
        });
    }

    // 2. Gráfico de Barras
    const ctxBarras = document.getElementById(`${prefixoId}-barras`);
    if (ctxBarras) {
        new Chart(ctxBarras, {
            type: "bar",
            data: {
                labels: ["Entradas", "Saídas"],
                datasets: [{
                    label: "R$",
                    data: [dColunas.entradas?.[0] || 0, dColunas.saidas?.[0] || 0],
                    backgroundColor: ["#10b981", "#ef4444"],
                    borderRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { ticks: { color: "#cbd5e1" }, grid: { display: false } },
                    y: { 
                        ticks: { 
                            color: "#cbd5e1",
                            callback: function(value) { return "R$ " + Number(value).toLocaleString("pt-BR"); }
                        }, 
                        grid: { color: "rgba(148, 163, 184, 0.1)" } 
                    }
                }
            }
        });
    }

    // 3. Gráfico de Linha (Evolução Forçada a Categoria no Eixo X para Expandir Horizontalmente)
    const ctxLinha = document.getElementById(`${prefixoId}-linha`);
    if (ctxLinha) {
        const { labelsNomes, saldos, detalhesTooltip, coresPontos } = resolverDadosEvolucaoComNomes(dEvolucao);

        new Chart(ctxLinha, {
            type: "line",
            data: {
                labels: labelsNomes,
                datasets: [{
                    label: "Saldo (R$)",
                    data: saldos,
                    borderColor: "#3b82f6",
                    backgroundColor: "rgba(59, 130, 246, 0.2)",
                    borderWidth: 2,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4.5,
                    pointHoverRadius: 6.5,
                    pointBackgroundColor: "#0f172a",
                    pointBorderColor: coresPontos,
                    pointBorderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            title: function(context) {
                                const idx = context[0]?.dataIndex ?? 0;
                                return detalhesTooltip[idx]?.titulo || context[0]?.label || "";
                            },
                            beforeBody: function(context) {
                                const idx = context[0]?.dataIndex ?? 0;
                                return detalhesTooltip[idx]?.movimento || "";
                            },
                            label: function(context) {
                                return ` Saldo Restante: ${formatarMoeda(context.parsed.y)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'category', // Trata strings sem colapsar os pontos
                        ticks: {
                            color: "#cbd5e1",
                            font: { size: 10 },
                            maxRotation: 25,
                            minRotation: 0,
                            callback: function(value) {
                                const labelText = this.getLabelForValue(value);
                                return labelText.length > 10 ? labelText.substring(0, 8) + "..." : labelText;
                            }
                        },
                        grid: { color: "rgba(148, 163, 184, 0.08)" }
                    },
                    y: {
                        ticks: {
                            color: "#cbd5e1",
                            font: { size: 10 },
                            callback: function(value) {
                                return "R$ " + Number(value).toLocaleString("pt-BR");
                            }
                        },
                        grid: { color: "rgba(148, 163, 184, 0.1)" }
                    }
                }
            }
        });
    }
}

async function enviarMensagemAoBot(mensagem) {
    adicionarBalaoMensagem("user", formatarMarkdownParaHTML(mensagem));

    try {
        const res = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ mensagem })
        });
        const data = await res.json();

        // Limpa cache antigo e atualiza a base de transações antes de desenhar 
        await carregarDadosUsuarioESaldo();

        const textoBot = formatarMarkdownParaHTML(data.resposta || "Comando processado.");
        
        // Puxa o objeto do novo `database.py` (dentro de "resumo" em vez de "graficos")
        let graficosChat = null;
        if (data.enviar_grafico || data.exibir_graficos || data.exibir_graficos_web || data.intencao === "enviar_grafico") {
            graficosChat = data.resumo || data.graficos || null;
        }

        adicionarBalaoMensagem("bot", textoBot, graficosChat);
        
        if (data.transacao_registrada) {
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
        }
    } catch (err) {
        adicionarBalaoMensagem("bot", "⚠️ Erro de comunicação com o servidor.");
    }
}

async function carregarDadosUsuarioESaldo() {
    try {
        const res = await fetch(`/api/dashboard/stats?_t=${Date.now()}`, { cache: "no-store" });
        if (!res.ok) return;
        const data = await res.json();
        if (!data.sucesso) return;

        listaTransacoesCache = Array.isArray(data.transacoes) ? data.transacoes : [];
        mapaTransacoesPorId = {};
        listaTransacoesCache.forEach((t) => {
            if (t.id != null) {
                mapaTransacoesPorId[String(t.id)] = t;
                mapaTransacoesPorId[`#${t.id}`] = t;
            }
        });

        const resumo = data.resumo;
        const elSaldo = document.getElementById("chat-header-saldo");
        if (elSaldo) {
            elSaldo.textContent = formatarMoeda(resumo.saldo);
            elSaldo.className = resumo.saldo < 0 ? "text-red" : "text-green";
        }

        const elGreeting = document.getElementById("chat-user-greeting");
        if (elGreeting && data.usuario && data.usuario.nome) {
            elGreeting.textContent = `Olá, ${data.usuario.nome}`;
        }
    } catch (e) {
        console.error("Erro ao carregar dados do usuário:", e);
    }
}