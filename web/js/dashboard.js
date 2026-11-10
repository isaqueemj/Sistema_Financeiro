// Caminho: web/js/dashboard.js
let instanciaChartPizza = null;
let instanciaChartColunas = null;
let instanciaChartLinha = null;

const PALETA_CORES = [
    "#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6",
    "#ec4899", "#06b6d4", "#f97316", "#14b8a6", "#6366f1"
];

function formatarMoedaBRL(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL"
    });
}

document.addEventListener("DOMContentLoaded", () => {
    carregarStatsDashboard(false);

    const selectPeriodo = document.getElementById("filtro-periodo");
    if (selectPeriodo) {
        selectPeriodo.addEventListener("change", () => {
            carregarStatsDashboard(true);
        });
    }

    const btnRefresh = document.getElementById("btn-refresh-dash");
    if (btnRefresh) {
        btnRefresh.addEventListener("click", (e) => {
            e.preventDefault();
            carregarStatsDashboard(true);
        });
    }

    window.addEventListener("storage", (e) => {
        if (e.key === "ultima_atualizacao_financeira") {
            carregarStatsDashboard(false);
        }
    });

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            carregarStatsDashboard(false);
        }
    });

    setInterval(() => carregarStatsDashboard(false), 10000);

    const formTransacao = document.getElementById("form-nova-transacao");
    if (formTransacao) {
        formTransacao.addEventListener("submit", registrarTransacaoManual);
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

async function carregarStatsDashboard(mostrarFeedbackBotao = false) {
    const selectPeriodo = document.getElementById("filtro-periodo");
    const btnRefresh = document.getElementById("btn-refresh-dash");
    const periodo = selectPeriodo ? selectPeriodo.value : "mes_atual";

    if (mostrarFeedbackBotao && btnRefresh) {
        btnRefresh.disabled = true;
        btnRefresh.textContent = "⏳ Atualizando...";
    }

    try {
        const url = `/api/dashboard/stats?periodo=${encodeURIComponent(periodo)}&_t=${Date.now()}`;
        const res = await fetch(url, { cache: "no-store" });

        if (res.status === 401) {
            window.location.href = "/";
            return;
        }

        const data = await res.json();
        if (!data.sucesso || !data.resumo) return;

        if (data.usuario && data.usuario.nome) {
            const elNome = document.getElementById("dash-user-name");
            if (elNome) elNome.textContent = `Olá, ${data.usuario.nome}`;
        }

        const subMes = document.getElementById("subtitulo-mes");
        if (subMes && data.resumo.mes_referencia) {
            subMes.textContent = `Referência: ${data.resumo.mes_referencia} — Valores consolidados (Fixos + Variáveis) em BRL`;
        }

        // 1. Atualiza Cards
        renderizarCardsValores(data.resumo);

        // 2. Gráfico de Pizza
        const dadosPizza = extrairDadosPizzaSeguros(data);
        renderizarGraficoPizza(dadosPizza);

        // 3. Gráfico de Colunas
        const dadosColunas = extrairDadosColunasSeguros(data);
        renderizarGraficoColunas(dadosColunas);

        // 4. Gráfico de Linha (Evolução do Saldo com nomes das transações)
        const dadosLinha = extrairDadosLinhaSeguros(data);
        renderizarGraficoLinha(dadosLinha);

        // 5. Atualiza Tabela
        renderizarTabelaMovimentacoes(data.transacoes || [], data.rendas_fixas || [], data.gastos_fixos || []);

        if (mostrarFeedbackBotao && btnRefresh) {
            btnRefresh.textContent = "✅ Atualizado!";
            setTimeout(() => {
                btnRefresh.disabled = false;
                btnRefresh.textContent = "🔄 Atualizar";
            }, 1200);
        }
    } catch (err) {
        console.error("Erro ao carregar Dashboard:", err);
        if (mostrarFeedbackBotao && btnRefresh) {
            btnRefresh.textContent = "❌ Erro";
            setTimeout(() => {
                btnRefresh.disabled = false;
                btnRefresh.textContent = "🔄 Atualizar";
            }, 1500);
        }
    }
}

function extrairDadosPizzaSeguros(data) {
    const resumo = data.resumo || {};
    const gp = data.grafico_pizza || resumo.grafico_pizza;

    if (gp && Array.isArray(gp.labels) && gp.labels.length > 0 && gp.valores.some((v) => Number(v) > 0)) {
        return { labels: gp.labels, valores: gp.valores.map(Number) };
    }

    if (Array.isArray(resumo.despesas_por_categoria) && resumo.despesas_por_categoria.length > 0) {
        return {
            labels: resumo.despesas_por_categoria.map((c) => c.categoria),
            valores: resumo.despesas_por_categoria.map((c) => Number(c.total))
        };
    }

    const mapa = {};
    (data.transacoes || []).forEach((t) => {
        if (t.tipo === "despesa") {
            const cat = t.categoria || "Outros";
            mapa[cat] = (mapa[cat] || 0) + Number(t.valor || 0);
        }
    });
    (data.gastos_fixos || []).filter((g) => g.is_active).forEach((g) => {
        const cat = `Fixo: ${g.description}`;
        mapa[cat] = (mapa[cat] || 0) + Number(g.amount || 0);
    });

    const chaves = Object.keys(mapa);
    if (chaves.length === 0 && Number(resumo.total_despesas) > 0) {
        return { labels: ["Despesas do Mês"], valores: [Number(resumo.total_despesas)] };
    }

    return {
        labels: chaves,
        valores: chaves.map((k) => Number(mapa[k].toFixed(2)))
    };
}

function extrairDadosColunasSeguros(data) {
    const resumo = data.resumo || {};
    const gc = data.grafico_colunas || resumo.grafico_colunas;

    if (gc && Array.isArray(gc.labels) && gc.labels.length > 0) {
        return {
            labels: gc.labels,
            entradas: gc.entradas.map(Number),
            saidas: gc.saidas.map(Number)
        };
    }

    return {
        labels: [resumo.mes_referencia || "Mês Vigente"],
        entradas: [Number(resumo.total_receitas || 0)],
        saidas: [Number(resumo.total_despesas || 0)]
    };
}

function extrairDadosLinhaSeguros(data) {
    const resumo = data.resumo || {};
    const transacoes = Array.isArray(data.transacoes) ? [...data.transacoes] : [];

    // Mapa de ID -> Nome da transação para substituir qualquer "#36" pelo nome real (ex: "Mercado")
    const mapaIdParaNome = {};
    transacoes.forEach((t) => {
        if (t.id != null) {
            mapaIdParaNome[`#${t.id}`] = (t.descricao || t.categoria || `Item #${t.id}`).trim();
        }
    });

    const totalRendasFixas = Number(
        resumo.total_rendas_fixas ??
        (data.rendas_fixas || []).filter((r) => r.is_active).reduce((acc, r) => acc + Number(r.amount || 0), 0)
    );
    const totalGastosFixos = Number(
        resumo.total_gastos_fixos ??
        (data.gastos_fixos || []).filter((g) => g.is_active).reduce((acc, g) => acc + Number(g.amount || 0), 0)
    );

    const baseFixa = Number((totalRendasFixas - totalGastosFixos).toFixed(2));

    // Ordena as transações da mais antiga para a mais recente para traçar a evolução real do saldo
    const transacoesOrdenadas = transacoes.sort((a, b) => {
        const idA = Number(a.id || 0);
        const idB = Number(b.id || 0);
        if (idA && idB) return idA - idB;
        return new Date(a.data_transacao || 0) - new Date(b.data_transacao || 0);
    });

    if (transacoesOrdenadas.length > 0 || baseFixa !== 0) {
        const labels = ["Base Fixa"];
        const saldos = [baseFixa];
        const detalhes = [
            `Base Fixa (Rendas Fixas - Gastos Fixos): ${formatarMoedaBRL(baseFixa)}`
        ];

        let saldoAcumulado = baseFixa;
        transacoesOrdenadas.forEach((t) => {
            const valor = Number(t.valor || 0);
            const ehReceita = t.tipo === "receita";
            saldoAcumulado = Number((saldoAcumulado + (ehReceita ? valor : -valor)).toFixed(2));

            const nomeTransacao = (t.descricao || t.categoria || "Movimentação").trim();
            labels.push(nomeTransacao);
            saldos.push(saldoAcumulado);
            detalhes.push(
                `${nomeTransacao} (${ehReceita ? "+" : "-"}${formatarMoedaBRL(valor)})`
            );
        });

        return { labels, saldos, detalhes };
    }

    // Fallback caso venha do objeto grafico_evolucao do backend
    const evolucaoBackend = data.grafico_evolucao || resumo.grafico_evolucao || data.graficos?.evolucao;
    if (evolucaoBackend && Array.isArray(evolucaoBackend.labels) && evolucaoBackend.labels.length > 0) {
        const labelsConvertidas = evolucaoBackend.labels.map((lbl) => mapaIdParaNome[lbl] || lbl);
        return {
            labels: labelsConvertidas,
            saldos: (evolucaoBackend.saldos || []).map(Number),
            detalhes: labelsConvertidas
        };
    }

    return {
        labels: ["Saldo Atual"],
        saldos: [Number(resumo.saldo || 0)],
        detalhes: [`Saldo Atual: ${formatarMoedaBRL(resumo.saldo || 0)}`]
    };
}

function renderizarCardsValores(resumo) {
    const elSaldo = document.getElementById("metric-saldo");
    const elReceitas = document.getElementById("metric-receitas");
    const elDespesas = document.getElementById("metric-despesas");
    const elStatus = document.getElementById("metric-status-orca");
    const elDetReceitas = document.getElementById("detalhe-receitas");
    const elDetDespesas = document.getElementById("detalhe-despesas");

    const totalEntradas = Number(resumo.total_receitas || 0);
    const totalSaidas = Number(resumo.total_despesas || 0);
    const saldoAtual = Number(resumo.saldo || 0);

    if (elSaldo) {
        elSaldo.textContent = formatarMoedaBRL(saldoAtual);
        elSaldo.className = `metric-value ${saldoAtual < 0 ? "text-red" : "text-green"}`;
    }
    if (elReceitas) elReceitas.textContent = formatarMoedaBRL(totalEntradas);
    if (elDespesas) elDespesas.textContent = formatarMoedaBRL(totalSaidas);

    if (elDetReceitas) {
        elDetReceitas.textContent = `Rendas Fixas: ${formatarMoedaBRL(resumo.total_rendas_fixas)} | Variáveis: ${formatarMoedaBRL(resumo.receitas_variaveis)}`;
    }
    if (elDetDespesas) {
        elDetDespesas.textContent = `Gastos Fixos: ${formatarMoedaBRL(resumo.total_gastos_fixos)} | Variáveis: ${formatarMoedaBRL(resumo.despesas_variaveis)}`;
    }

    if (elStatus) {
        if (totalEntradas === 0 && totalSaidas === 0) {
            elStatus.textContent = "💡 Cadastre rendas ou despesas para iniciar a análise";
        } else if (saldoAtual < 0) {
            elStatus.textContent = "⚠️ Atenção (RN02): Saídas superaram as entradas do período!";
        } else {
            const comprometimento = totalEntradas > 0 ? ((totalSaidas / totalEntradas) * 100).toFixed(1) : 0;
            elStatus.textContent = `✅ Orçamento positivo (${comprometimento}% da renda comprometida)`;
        }
    }
}

function renderizarGraficoPizza(dadosPizza) {
    const canvas = document.getElementById("chart-pizza");
    const fallbackDiv = document.getElementById("fallback-pizza");
    const msgVazio = document.getElementById("pizza-empty");

    const labels = dadosPizza.labels || [];
    const valores = dadosPizza.valores || [];
    const totalGeral = valores.reduce((acc, v) => acc + Number(v || 0), 0);

    if (labels.length === 0 || totalGeral <= 0) {
        if (canvas) canvas.style.display = "none";
        if (fallbackDiv) fallbackDiv.style.display = "none";
        if (msgVazio) msgVazio.style.display = "block";
        if (instanciaChartPizza) {
            instanciaChartPizza.destroy();
            instanciaChartPizza = null;
        }
        return;
    }

    if (msgVazio) msgVazio.style.display = "none";

    if (typeof Chart !== "undefined" && canvas) {
        if (fallbackDiv) fallbackDiv.style.display = "none";
        canvas.style.display = "block";

        if (instanciaChartPizza) {
            instanciaChartPizza.data.labels = labels;
            instanciaChartPizza.data.datasets[0].data = valores;
            instanciaChartPizza.data.datasets[0].backgroundColor = PALETA_CORES.slice(0, labels.length);
            instanciaChartPizza.update();
            return;
        }

        const ctx = canvas.getContext("2d");
        instanciaChartPizza = new Chart(ctx, {
            type: "doughnut",
            data: {
                labels: labels,
                datasets: [{
                    data: valores,
                    backgroundColor: PALETA_CORES.slice(0, labels.length),
                    borderColor: "#152238",
                    borderWidth: 2,
                    hoverOffset: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "right",
                        labels: { color: "#cbd5e1", font: { size: 12 }, padding: 14 }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                const val = context.parsed || 0;
                                const perc = totalGeral > 0 ? ((val / totalGeral) * 100).toFixed(1) : 0;
                                return ` ${context.label}: ${formatarMoedaBRL(val)} (${perc}%)`;
                            }
                        }
                    }
                }
            }
        });
    } else if (fallbackDiv) {
        if (canvas) canvas.style.display = "none";
        fallbackDiv.style.display = "flex";
        desenharPizzaSVGNativo(fallbackDiv, labels, valores, totalGeral);
    }
}

function renderizarGraficoColunas(dadosColunas) {
    const canvas = document.getElementById("chart-colunas");
    const fallbackDiv = document.getElementById("fallback-colunas");

    const labels = dadosColunas.labels || ["Mês Atual"];
    const entradas = dadosColunas.entradas || [0];
    const saidas = dadosColunas.saidas || [0];

    if (typeof Chart !== "undefined" && canvas) {
        if (fallbackDiv) fallbackDiv.style.display = "none";
        canvas.style.display = "block";

        if (instanciaChartColunas) {
            instanciaChartColunas.data.labels = labels;
            instanciaChartColunas.data.datasets[0].data = entradas;
            instanciaChartColunas.data.datasets[1].data = saidas;
            instanciaChartColunas.update();
            return;
        }

        const ctx = canvas.getContext("2d");
        instanciaChartColunas = new Chart(ctx, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [
                    {
                        label: "Entradas (Receitas)",
                        data: entradas,
                        backgroundColor: "rgba(16, 185, 129, 0.85)",
                        borderColor: "#10b981",
                        borderWidth: 1,
                        borderRadius: 6
                    },
                    {
                        label: "Saídas (Gastos)",
                        data: saidas,
                        backgroundColor: "rgba(239, 68, 68, 0.85)",
                        borderColor: "#ef4444",
                        borderWidth: 1,
                        borderRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        ticks: { color: "#94a3b8" },
                        grid: { color: "rgba(148, 163, 184, 0.08)" }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: "#94a3b8",
                            callback: function(value) {
                                return "R$ " + Number(value).toLocaleString("pt-BR");
                            }
                        },
                        grid: { color: "rgba(148, 163, 184, 0.1)" }
                    }
                },
                plugins: {
                    legend: {
                        position: "top",
                        labels: { color: "#e2e8f0", font: { size: 12 } }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return ` ${context.dataset.label}: ${formatarMoedaBRL(context.parsed.y)}`;
                            }
                        }
                    }
                }
            }
        });
    } else if (fallbackDiv) {
        if (canvas) canvas.style.display = "none";
        fallbackDiv.style.display = "flex";
        desenharColunasSVGNativo(fallbackDiv, labels, entradas, saidas);
    }
}

function renderizarGraficoLinha(dadosLinha) {
    const canvas = document.getElementById("chart-linha-tendencia");
    const fallbackDiv = document.getElementById("fallback-linha");
    const msgVazio = document.getElementById("linha-empty");

    const labels = dadosLinha.labels || [];
    const saldos = dadosLinha.saldos || [];
    const detalhes = dadosLinha.detalhes || [];

    if (labels.length === 0 || saldos.length === 0) {
        if (canvas) canvas.style.display = "none";
        if (fallbackDiv) fallbackDiv.style.display = "none";
        if (msgVazio) msgVazio.style.display = "block";
        if (instanciaChartLinha) {
            instanciaChartLinha.destroy();
            instanciaChartLinha = null;
        }
        return;
    }

    if (msgVazio) msgVazio.style.display = "none";

    if (typeof Chart !== "undefined" && canvas) {
        if (fallbackDiv) fallbackDiv.style.display = "none";
        canvas.style.display = "block";

        if (instanciaChartLinha) {
            instanciaChartLinha.data.labels = labels;
            instanciaChartLinha.data.datasets[0].data = saldos;
            instanciaChartLinha.options.plugins.tooltip.detalhes = detalhes;
            instanciaChartLinha.update();
            return;
        }

        const ctx = canvas.getContext("2d");
        instanciaChartLinha = new Chart(ctx, {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    label: "Saldo (R$)",
                    data: saldos,
                    borderColor: "#3b82f6",
                    backgroundColor: "rgba(59, 130, 246, 0.22)",
                    borderWidth: 2.5,
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                    pointBackgroundColor: "#152238",
                    pointBorderColor: "#3b82f6",
                    pointBorderWidth: 2
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "top",
                        labels: {
                            color: "#f8fafc",
                            font: { size: 12 }
                        }
                    },
                    tooltip: {
                        detalhes: detalhes,
                        callbacks: {
                            title: function(context) {
                                const idx = context[0]?.dataIndex ?? 0;
                                const listaDet = context[0]?.chart?.options?.plugins?.tooltip?.detalhes || [];
                                return listaDet[idx] || context[0]?.label || "";
                            },
                            label: function(context) {
                                const val = context.parsed.y || 0;
                                return ` Saldo Acumulado: ${formatarMoedaBRL(val)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: "#cbd5e1" },
                        grid: { color: "rgba(148, 163, 184, 0.08)" }
                    },
                    y: {
                        ticks: {
                            color: "#cbd5e1",
                            callback: function(value) {
                                return Number(value).toLocaleString("pt-BR");
                            }
                        },
                        grid: { color: "rgba(148, 163, 184, 0.1)" }
                    }
                }
            }
        });
    } else if (fallbackDiv) {
        if (canvas) canvas.style.display = "none";
        fallbackDiv.style.display = "flex";
        desenharLinhaSVGNativo(fallbackDiv, labels, saldos);
    }
}

/* ==================== RENDERIZADORES NATIVOS SVG (FALLBACK SEM CDN) ==================== */

function desenharPizzaSVGNativo(container, labels, valores, totalGeral) {
    let acumulado = 0;
    const fatias = valores.map((val, i) => {
        const proporcao = val / totalGeral;
        const inicio = acumulado * 100;
        acumulado += proporcao;
        const fim = acumulado * 100;
        const cor = PALETA_CORES[i % PALETA_CORES.length];
        return `${cor} ${inicio.toFixed(2)}% ${fim.toFixed(2)}%`;
    }).join(", ");

    const legendaHtml = labels.map((lbl, i) => {
        const val = valores[i];
        const perc = ((val / totalGeral) * 100).toFixed(1);
        const cor = PALETA_CORES[i % PALETA_CORES.length];
        return `
            <div style="display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:8px; font-size:0.85rem;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="width:12px; height:12px; border-radius:3px; background:${cor}; display:inline-block;"></span>
                    <span style="color:#e2e8f0;">${lbl}</span>
                </div>
                <strong style="color:#cbd5e1;">${formatarMoedaBRL(val)} (${perc}%)</strong>
            </div>
        `;
    }).join("");

    container.innerHTML = `
        <div style="display:flex; align-items:center; justify-content:space-around; width:100%; height:100%; gap:1.2rem; padding:0.5rem;">
            <div style="position:relative; width:175px; height:175px; border-radius:50%; background:conic-gradient(${fatias}); display:flex; align-items:center; justify-content:center; flex-shrink:0; box-shadow:0 4px 15px rgba(0,0,0,0.35);">
                <div style="width:105px; height:105px; border-radius:50%; background:#152238; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; padding:5px;">
                    <span style="font-size:0.7rem; color:#94a3b8;">Total Gastos</span>
                    <strong style="font-size:0.88rem; color:#f8fafc;">${formatarMoedaBRL(totalGeral)}</strong>
                </div>
            </div>
            <div style="flex:1; max-height:240px; overflow-y:auto; padding-right:6px;">
                ${legendaHtml}
            </div>
        </div>
    `;
}

function desenharColunasSVGNativo(container, labels, entradas, saidas) {
    const maiorValor = Math.max(...entradas, ...saidas, 100);
    const colunasHtml = labels.map((mes, i) => {
        const valEnt = Number(entradas[i] || 0);
        const valSai = Number(saidas[i] || 0);
        const altEnt = Math.max((valEnt / maiorValor) * 180, valEnt > 0 ? 8 : 2);
        const altSai = Math.max((valSai / maiorValor) * 180, valSai > 0 ? 8 : 2);

        return `
            <div style="display:flex; flex-direction:column; align-items:center; flex:1; min-width:48px;">
                <div style="display:flex; align-items:flex-end; justify-content:center; gap:6px; height:190px; width:100%; border-bottom:1px solid #334155; padding-bottom:4px;">
                    <div title="Entradas (${mes}): ${formatarMoedaBRL(valEnt)}"
                         style="width:18px; height:${altEnt}px; background:linear-gradient(180deg, #10b981, #059669); border-radius:4px 4px 0 0; transition:height 0.3s;"></div>
                    <div title="Saídas (${mes}): ${formatarMoedaBRL(valSai)}"
                         style="width:18px; height:${altSai}px; background:linear-gradient(180deg, #ef4444, #dc2626); border-radius:4px 4px 0 0; transition:height 0.3s;"></div>
                </div>
                <span style="margin-top:8px; font-size:0.78rem; color:#94a3b8; font-weight:600;">${mes}</span>
            </div>
        `;
    }).join("");

    container.innerHTML = `
        <div style="display:flex; flex-direction:column; width:100%; height:100%; justify-content:space-between; padding:0.5rem;">
            <div style="display:flex; justify-content:center; gap:20px; font-size:0.82rem; color:#e2e8f0; margin-bottom:6px;">
                <span><strong style="color:#10b981;">■</strong> Entradas (Receitas)</span>
                <span><strong style="color:#ef4444;">■</strong> Saídas (Gastos)</span>
            </div>
            <div style="display:flex; align-items:flex-end; justify-content:space-around; gap:10px; flex:1; padding:0 10px;">
                ${colunasHtml}
            </div>
        </div>
    `;
}

function desenharLinhaSVGNativo(container, labels, saldos) {
    const largura = 700;
    const altura = 200;
    const padX = 45;
    const padY = 25;

    const minVal = Math.min(...saldos);
    const maxVal = Math.max(...saldos);
    const amplitude = maxVal - minVal || 1;

    const pontos = saldos.map((val, idx) => {
        const x = padX + (labels.length > 1 ? (idx / (labels.length - 1)) * (largura - padX * 2) : (largura / 2));
        const y = altura - padY - ((val - minVal) / amplitude) * (altura - padY * 2);
        return { x, y, val, label: labels[idx] };
    });

    const caminhoLinha = pontos.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
    const caminhoArea = `${caminhoLinha} L ${pontos[pontos.length - 1].x.toFixed(1)} ${altura - padY} L ${pontos[0].x.toFixed(1)} ${altura - padY} Z`;

    const circulosHtml = pontos.map((p) => `
        <circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="4.5" fill="#152238" stroke="#3b82f6" stroke-width="2.5">
            <title>${p.label}: ${formatarMoedaBRL(p.val)}</title>
        </circle>
        <text x="${p.x.toFixed(1)}" y="${altura - 6}" fill="#cbd5e1" font-size="11" text-anchor="middle">${p.label}</text>
    `).join("");

    container.innerHTML = `
        <svg viewBox="0 0 ${largura} ${altura}" style="width:100%; height:100%; overflow:visible;">
            <path d="${caminhoArea}" fill="rgba(59, 130, 246, 0.22)"></path>
            <path d="${caminhoLinha}" fill="none" stroke="#3b82f6" stroke-width="2.5"></path>
            ${circulosHtml}
        </svg>
    `;
}

function renderizarTabelaMovimentacoes(transacoes = [], rendasFixas = [], gastosFixos = []) {
    const tbody = document.getElementById("tabela-transacoes-body");
    if (!tbody) return;

    const itensUnificados = [];

    rendasFixas.filter((r) => r.is_active).forEach((r) => {
        itensUnificados.push({
            dataExibicao: `Dia ${r.day_of_month} (Fixo)`,
            descricao: r.description,
            categoria: "Renda Fixa Mensal",
            tipo: "receita",
            valor: Number(r.amount)
        });
    });

    gastosFixos.filter((g) => g.is_active).forEach((g) => {
        itensUnificados.push({
            dataExibicao: `Venc. Dia ${g.due_day} (Fixo)`,
            descricao: g.description,
            categoria: "Gasto Fixo Mensal",
            tipo: "despesa",
            valor: Number(g.amount)
        });
    });

    transacoes.forEach((t) => {
        const dataFmt = t.data_transacao
            ? new Date(t.data_transacao.replace(" ", "T")).toLocaleDateString("pt-BR")
            : "-";
        itensUnificados.push({
            dataExibicao: dataFmt,
            descricao: t.descricao || t.categoria,
            categoria: t.categoria,
            tipo: t.tipo,
            valor: Number(t.valor)
        });
    });

    if (itensUnificados.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="empty-msg">
                    Nenhuma movimentação encontrada. Cadastre no formulário ao lado ou envie uma mensagem no Assistente IA!
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = itensUnificados.map((item) => {
        const ehReceita = item.tipo === "receita";
        return `
            <tr>
                <td>${item.dataExibicao}</td>
                <td><strong>${item.descricao}</strong></td>
                <td>${item.categoria}</td>
                <td>
                    <span class="badge-tipo ${ehReceita ? "badge-receita" : "badge-despesa"}">
                        ${ehReceita ? "Entrada" : "Saída"}
                    </span>
                </td>
                <td class="${ehReceita ? "text-green" : "text-red"}" style="font-weight: 700;">
                    ${ehReceita ? "+" : "-"} ${formatarMoedaBRL(item.valor)}
                </td>
            </tr>
        `;
    }).join("");
}

async function registrarTransacaoManual(e) {
    e.preventDefault();
    const tipo = document.getElementById("trans-tipo").value;
    const valor = parseFloat(document.getElementById("trans-valor").value);
    const categoria = document.getElementById("trans-categoria").value;
    const descricao = document.getElementById("trans-descricao").value.trim();
    const alertBox = document.getElementById("dash-alert");

    try {
        const res = await fetch("/api/transacoes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tipo, valor, categoria, descricao, moeda: "BRL" })
        });
        const data = await res.json();
        alertBox.style.display = "block";

        if (res.ok && data.sucesso) {
            alertBox.className = "alert-box alert-success";
            alertBox.textContent = data.alerta || "Movimentação registrada e gráficos atualizados!";
            document.getElementById("form-nova-transacao").reset();
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            await carregarStatsDashboard(true);
            setTimeout(() => { alertBox.style.display = "none"; }, 4000);
        } else {
            alertBox.className = "alert-box alert-error";
            alertBox.textContent = data.erro || "Erro ao registrar transação.";
        }
    } catch (err) {
        alertBox.style.display = "block";
        alertBox.className = "alert-box alert-error";
        alertBox.textContent = "Erro de conexão com o servidor.";
    }
}