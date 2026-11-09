// Caminho: web/js/teto_gastos.js
let instanciaChartTetos = null;
let cacheTetosAtuais = [];

const CATEGORIAS_PADRAO = [
    "Alimentação", "Moradia", "Transporte", "Lazer",
    "Saúde", "Educação", "Vestuário", "Outros"
];

function formatarMoedaBRL(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL"
    });
}

// Garante que o layout lado a lado, barras de progresso e botões Editar/Excluir funcionem mesmo com cache de CSS
function garantirEstilosTetoGastos() {
    let style = document.getElementById("estilo-fallback-tetos");
    if (!style) {
        style = document.createElement("style");
        style.id = "estilo-fallback-tetos";
        document.head.appendChild(style);
    }

    style.textContent = `
        /* Espaçamento entre todas as seções e formulários */
        .metrics-grid {
            margin-bottom: 2rem !important;
            gap: 1.5rem !important;
        }
        .chart-teto-section {
            margin-bottom: 2rem !important;
        }
        .teto-chart-wrapper {
            position: relative;
            height: 250px;
            width: 100%;
            margin-top: 1rem;
        }

        /* Dois formulários lado a lado com espaço entre eles */
        .forms-columns-grid {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 1.8rem !important;
            margin-bottom: 2rem !important;
            align-items: stretch !important;
            width: 100% !important;
        }

        .form-card-col {
            display: flex !important;
            flex-direction: column !important;
            justify-content: space-between !important;
            padding: 1.6rem !important;
            min-width: 0 !important;
        }

        #form-teto-gasto,
        #form-gasto-rapido-teto {
            display: flex !important;
            flex-direction: column !important;
            gap: 1.1rem !important;
            margin-top: 0.6rem !important;
        }

        .form-row-cols {
            display: grid !important;
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
            gap: 1rem !important;
            align-items: start !important;
        }

        .form-row-cols.align-end {
            align-items: end !important;
        }

        .form-card-col .form-group {
            margin-bottom: 0 !important;
            display: flex !important;
            flex-direction: column !important;
            gap: 0.45rem !important;
            min-width: 0 !important;
        }

        .form-card-col label {
            display: block !important;
            font-size: 0.85rem !important;
            font-weight: 600 !important;
            color: #cbd5e1 !important;
            margin-bottom: 0 !important;
        }

        .form-card-col input,
        .form-card-col select {
            width: 100% !important;
            padding: 0.75rem 0.9rem !important;
            border-radius: 8px !important;
            border: 1px solid #334155 !important;
            background-color: #0f172a !important;
            color: #f8fafc !important;
            font-size: 0.9rem !important;
            box-sizing: border-box !important;
        }

        .form-card-col input:focus,
        .form-card-col select:focus {
            outline: none !important;
            border-color: #3b82f6 !important;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.18) !important;
        }

        /* Botões dos formulários */
        .form-actions-teto {
            display: flex !important;
            flex-direction: row !important;
            gap: 0.6rem !important;
            width: 100% !important;
        }

        .form-actions-teto .btn-submit-trans {
            flex: 1 !important;
            padding: 0.78rem 1rem !important;
            border-radius: 8px !important;
            font-weight: 700 !important;
            font-size: 0.9rem !important;
            cursor: pointer !important;
            border: none !important;
            color: #ffffff !important;
            background: #3b82f6 !important;
            transition: all 0.2s ease !important;
        }

        .form-actions-teto .btn-submit-trans:hover {
            background: #2563eb !important;
        }

        .btn-submit-green {
            background: linear-gradient(135deg, #10b981, #059669) !important;
        }

        .btn-submit-green:hover {
            box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35) !important;
        }

        .btn-cancel-edit {
            padding: 0.78rem 1rem !important;
            background: transparent !important;
            color: #cbd5e1 !important;
            border: 1px solid #475569 !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            cursor: pointer !important;
        }

        .btn-cancel-edit:hover {
            background: #1e293b !important;
            color: #ffffff !important;
        }

        /* Caixas inferiores dos formulários (Dica IA e Barra de Progresso do Simulador) */
        .chat-tip-box,
        .simulador-preview-box {
            margin-top: 1.2rem !important;
            padding: 0.95rem 1.1rem !important;
            background: rgba(15, 23, 42, 0.8) !important;
            border: 1px dashed #334155 !important;
            border-radius: 10px !important;
            font-size: 0.82rem !important;
            color: #94a3b8 !important;
        }

        .chat-tip-box code {
            display: inline-block;
            margin-top: 0.25rem;
            padding: 0.18rem 0.5rem;
            background: #0b1320;
            color: #6ee7b7;
            border-radius: 6px;
            font-family: monospace;
        }

        .simulador-preview-header {
            display: flex !important;
            justify-content: space-between !important;
            align-items: center !important;
            margin-bottom: 0.45rem !important;
            color: #e2e8f0 !important;
            font-size: 0.82rem !important;
        }

        .simulador-preview-box small {
            display: block !important;
            margin-top: 0.45rem !important;
            color: #94a3b8 !important;
            font-size: 0.78rem !important;
        }

        /* Tabela em largura total abaixo dos 2 formulários */
        .table-full-card {
            width: 100% !important;
            margin-bottom: 2rem !important;
            padding: 1.6rem !important;
        }

        /* Barras de Progresso (Tabela e Simulador) */
        .progress-cell {
            min-width: 190px !important;
            width: 28% !important;
        }

        .progress-info {
            display: flex !important;
            justify-content: space-between !important;
            font-size: 0.78rem !important;
            color: #94a3b8 !important;
            margin-bottom: 0.35rem !important;
        }

        .progress-track {
            width: 100% !important;
            height: 10px !important;
            background-color: #0b1320 !important;
            border-radius: 999px !important;
            overflow: hidden !important;
            border: 1px solid #1e293b !important;
        }

        .progress-bar-fill {
            height: 100% !important;
            border-radius: 999px !important;
            transition: width 0.35s ease !important;
        }

        .fill-safe {
            background: linear-gradient(90deg, #10b981, #059669) !important;
        }

        .fill-warning {
            background: linear-gradient(90deg, #f59e0b, #d97706) !important;
        }

        .fill-danger {
            background: linear-gradient(90deg, #ef4444, #dc2626) !important;
        }

        /* Badges de Status */
        .badge-status-teto {
            padding: 0.32rem 0.72rem !important;
            border-radius: 999px !important;
            font-size: 0.75rem !important;
            font-weight: 700 !important;
            display: inline-block !important;
            white-space: nowrap !important;
        }

        .status-ok {
            background: rgba(16, 185, 129, 0.16) !important;
            color: #6ee7b7 !important;
            border: 1px solid rgba(16, 185, 129, 0.35) !important;
        }

        .status-warn {
            background: rgba(245, 158, 11, 0.16) !important;
            color: #fcd34d !important;
            border: 1px solid rgba(245, 158, 11, 0.35) !important;
        }

        .status-danger {
            background: rgba(239, 68, 68, 0.18) !important;
            color: #fca5a5 !important;
            border: 1px solid rgba(239, 68, 68, 0.4) !important;
        }

        /* Botões Editar e Excluir estilizados */
        .teto-actions {
            display: flex !important;
            flex-direction: row !important;
            gap: 0.5rem !important;
            align-items: center !important;
            justify-content: flex-end !important;
            white-space: nowrap !important;
        }

        .btn-action-edit,
        .btn-action-del {
            padding: 0.42rem 0.8rem !important;
            border-radius: 8px !important;
            font-size: 0.78rem !important;
            font-weight: 600 !important;
            cursor: pointer !important;
            transition: all 0.2s ease !important;
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 0.3rem !important;
            white-space: nowrap !important;
        }

        .btn-action-edit {
            background: rgba(59, 130, 246, 0.16) !important;
            color: #93c5fd !important;
            border: 1px solid rgba(59, 130, 246, 0.45) !important;
        }

        .btn-action-edit:hover {
            background: #3b82f6 !important;
            color: #ffffff !important;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.35) !important;
            transform: translateY(-1px) !important;
        }

        .btn-action-del {
            background: rgba(239, 68, 68, 0.16) !important;
            color: #fca5a5 !important;
            border: 1px solid rgba(239, 68, 68, 0.45) !important;
        }

        .btn-action-del:hover {
            background: #ef4444 !important;
            color: #ffffff !important;
            box-shadow: 0 4px 12px rgba(239, 68, 68, 0.35) !important;
            transform: translateY(-1px) !important;
        }

        @media (max-width: 1080px) {
            .forms-columns-grid {
                grid-template-columns: 1fr !important;
            }
        }

        @media (max-width: 640px) {
            .form-row-cols {
                grid-template-columns: 1fr !important;
            }
        }
    `;
}

// Organiza os 2 formulários lado a lado e a tabela abaixo
function garantirLayoutColunasDOM() {
    const oldColumns = document.querySelector(".dashboard-columns");
    if (oldColumns && !document.querySelector(".forms-columns-grid")) {
        const colLeftCard = oldColumns.querySelector(".col-left .panel-card");
        const colRightCard = oldColumns.querySelector(".col-right");

        if (colLeftCard && colRightCard) {
            const formsGrid = document.createElement("section");
            formsGrid.className = "forms-columns-grid";
            colLeftCard.classList.add("form-card-col");

            const novoCardSimulador = document.createElement("div");
            novoCardSimulador.className = "panel-card form-card-col";
            novoCardSimulador.innerHTML = `
                <div class="panel-header-inline">
                    <div>
                        <h2>⚡ Lançar Gasto e Simular Impacto</h2>
                        <p class="chart-subtitle">Veja o impacto na barra de progresso antes de confirmar o lançamento</p>
                    </div>
                </div>
                <div id="simulador-alert" class="alert-box"></div>
                <form id="form-gasto-rapido-teto">
                    <div class="form-row-cols">
                        <div class="form-group">
                            <label for="rapido-categoria">Categoria do Gasto</label>
                            <select id="rapido-categoria" required>
                                <option value="Alimentação">🛒 Alimentação</option>
                                <option value="Transporte">🚗 Transporte</option>
                                <option value="Moradia">🏠 Moradia</option>
                                <option value="Lazer">🎬 Lazer</option>
                                <option value="Saúde">💊 Saúde</option>
                                <option value="Educação">📚 Educação</option>
                                <option value="Vestuário">👕 Vestuário</option>
                                <option value="Outros">📌 Outros</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <label for="rapido-valor">Valor do Gasto (R$)</label>
                            <input type="number" id="rapido-valor" step="0.01" min="0.01" required placeholder="Ex: 45.00">
                        </div>
                    </div>
                    <div class="form-row-cols align-end">
                        <div class="form-group">
                            <label for="rapido-descricao">Descrição / Local</label>
                            <input type="text" id="rapido-descricao" required placeholder="Ex: Uber, Mercado, Farmácia">
                        </div>
                        <div class="form-actions-teto">
                            <button type="submit" class="btn-submit-trans btn-submit-green" id="btn-lancar-rapido">
                                Registrar Gasto
                            </button>
                        </div>
                    </div>
                </form>
                <div class="simulador-preview-box" id="box-preview-impacto">
                    <div class="simulador-preview-header">
                        <span id="preview-texto-cat">📊 Simulação de Impacto no Teto</span>
                        <strong id="preview-perc-futuro">0.0%</strong>
                    </div>
                    <div class="progress-track">
                        <div id="preview-barra-fill" class="progress-bar-fill fill-safe" style="width: 0%;"></div>
                    </div>
                    <small id="preview-detalhe-margem">Digite um valor acima para simular o consumo da categoria.</small>
                </div>
            `;

            formsGrid.appendChild(colLeftCard);
            formsGrid.appendChild(novoCardSimulador);

            colRightCard.classList.remove("col-right");
            colRightCard.classList.add("table-full-card");

            oldColumns.parentNode.insertBefore(formsGrid, oldColumns);
            oldColumns.parentNode.insertBefore(colRightCard, oldColumns);
            oldColumns.remove();
        }
    }
}

document.addEventListener("DOMContentLoaded", () => {
    garantirEstilosTetoGastos();
    garantirLayoutColunasDOM();
    carregarTetosGastos();

    // Alternar entre Categoria Oficial e Item Específico no formulário 1
    const selectTipoAlvo = document.getElementById("select-tipo-alvo");
    if (selectTipoAlvo) {
        selectTipoAlvo.addEventListener("change", alternarCampoAlvo);
    }

    // Submissão do formulário 1: Teto de Gastos
    const formTeto = document.getElementById("form-teto-gasto");
    if (formTeto) {
        formTeto.addEventListener("submit", salvarTetoGasto);
    }

    // Botão Cancelar Edição
    const btnCancelar = document.getElementById("btn-cancelar-edicao");
    if (btnCancelar) {
        btnCancelar.addEventListener("click", resetarFormularioTeto);
    }

    // Submissão e Simulação em Tempo Real do formulário 2: Gasto Rápido
    const formRapido = document.getElementById("form-gasto-rapido-teto");
    const inputRapidoCat = document.getElementById("rapido-categoria");
    const inputRapidoVal = document.getElementById("rapido-valor");

    if (inputRapidoCat) inputRapidoCat.addEventListener("change", atualizarSimulacaoImpacto);
    if (inputRapidoVal) inputRapidoVal.addEventListener("input", atualizarSimulacaoImpacto);
    if (formRapido) formRapido.addEventListener("submit", registrarGastoRapidoNoTeto);

    // Botão Atualizar
    const btnRefresh = document.getElementById("btn-refresh-tetos");
    if (btnRefresh) {
        btnRefresh.addEventListener("click", () => carregarTetosGastos(true));
    }

    // Delegação de eventos para os botões Editar e Excluir da tabela
    const tbody = document.getElementById("tabela-tetos-body");
    if (tbody) {
        tbody.addEventListener("click", (e) => {
            const btnEdit = e.target.closest(".btn-action-edit");
            if (btnEdit) {
                const categoria = btnEdit.getAttribute("data-categoria");
                const valor = parseFloat(btnEdit.getAttribute("data-valor") || "0");
                prepararEdicaoTeto(categoria, valor);
                return;
            }

            const btnDel = e.target.closest(".btn-action-del");
            if (btnDel) {
                const categoria = btnDel.getAttribute("data-categoria");
                excluirTeto(categoria);
            }
        });
    }

    // Sincronização em tempo real
    window.addEventListener("storage", (e) => {
        if (e.key === "ultima_atualizacao_financeira") {
            carregarTetosGastos();
        }
    });

    document.addEventListener("visibilitychange", () => {
        if (!document.hidden) {
            carregarTetosGastos();
        }
    });

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

function alternarCampoAlvo() {
    const tipo = document.getElementById("select-tipo-alvo").value;
    const boxCat = document.getElementById("box-select-categoria");
    const boxItem = document.getElementById("box-input-item");

    if (tipo === "item") {
        boxCat.style.display = "none";
        boxItem.style.display = "flex";
        document.getElementById("input-item-especifico").focus();
    } else {
        boxCat.style.display = "flex";
        boxItem.style.display = "none";
    }
}

function exibirAlertaBox(elementId, mensagem, tipo = "success") {
    const box = document.getElementById(elementId);
    if (!box) return;
    box.className = `alert-box ${tipo === "success" ? "alert-success" : "alert-error"}`;
    box.textContent = mensagem;
    box.style.display = "block";
    setTimeout(() => {
        box.style.display = "none";
    }, 4000);
}

function exibirAlertaTeto(mensagem, tipo = "success") {
    exibirAlertaBox("teto-alert", mensagem, tipo);
}

async function carregarTetosGastos(mostrarFeedback = false) {
    const btnRefresh = document.getElementById("btn-refresh-tetos");
    if (mostrarFeedback && btnRefresh) {
        btnRefresh.disabled = true;
        btnRefresh.textContent = "⏳ Atualizando...";
    }

    try {
        const res = await fetch(`/api/tetos?_t=${Date.now()}`, {
            method: "GET",
            credentials: "same-origin",
            cache: "no-store"
        });

        if (res.status === 401) {
            window.location.href = "/";
            return;
        }

        const data = await res.json();
        if (!data.sucesso) return;

        if (data.usuario && data.usuario.nome) {
            const elUser = document.getElementById("teto-user-name");
            if (elUser) elUser.textContent = `Olá, ${data.usuario.nome}`;
        }

        const tetos = data.tetos || [];
        cacheTetosAtuais = tetos;

        renderizarCardsTetos(tetos);
        renderizarGraficoComparativoTetos(tetos);
        renderizarTabelaTetos(tetos);
        atualizarOpcoesCategoriaSimulador(tetos);
        atualizarSimulacaoImpacto();

        if (mostrarFeedback && btnRefresh) {
            btnRefresh.textContent = "✅ Atualizado!";
            setTimeout(() => {
                btnRefresh.disabled = false;
                btnRefresh.textContent = "🔄 Atualizar";
            }, 1000);
        }
    } catch (err) {
        console.error("Erro ao carregar tetos de gastos:", err);
        if (mostrarFeedback && btnRefresh) {
            btnRefresh.disabled = false;
            btnRefresh.textContent = "🔄 Atualizar";
        }
    }
}

function atualizarOpcoesCategoriaSimulador(tetos) {
    const selectRapido = document.getElementById("rapido-categoria");
    if (!selectRapido) return;

    const valorAnterior = selectRapido.value;
    const nomesCategorias = new Set(CATEGORIAS_PADRAO);
    tetos.forEach((t) => {
        if (t.categoria) nomesCategorias.add(t.categoria);
    });

    selectRapido.innerHTML = Array.from(nomesCategorias).map((cat) => {
        return `<option value="${cat}">${cat}</option>`;
    }).join("");

    if (valorAnterior && nomesCategorias.has(valorAnterior)) {
        selectRapido.value = valorAnterior;
    } else if (tetos.length > 0) {
        selectRapido.value = tetos[0].categoria;
    }
}

function atualizarSimulacaoImpacto() {
    const selectCat = document.getElementById("rapido-categoria");
    const inputVal = document.getElementById("rapido-valor");
    const elTextoCat = document.getElementById("preview-texto-cat");
    const elPercFuturo = document.getElementById("preview-perc-futuro");
    const elBarraFill = document.getElementById("preview-barra-fill");
    const elDetalhe = document.getElementById("preview-detalhe-margem");

    if (!selectCat || !elTextoCat || !elPercFuturo || !elBarraFill || !elDetalhe) return;

    const categoria = selectCat.value;
    const valorAdicional = parseFloat(String(inputVal?.value || "0").replace(",", ".")) || 0;

    const tetoEncontrado = cacheTetosAtuais.find(
        (t) => String(t.categoria).toLowerCase() === String(categoria).toLowerCase()
    );

    if (!tetoEncontrado) {
        elTextoCat.textContent = `📊 ${categoria} (Sem teto definido)`;
        elPercFuturo.textContent = "0.0%";
        elBarraFill.style.width = "0%";
        elBarraFill.className = "progress-bar-fill fill-safe";
        elDetalhe.textContent = "Defina um teto no formulário ao lado para acompanhar a barra de progresso desta categoria.";
        return;
    }

    const gastoAtual = Number(tetoEncontrado.gasto_atual || 0);
    const valorTeto = Number(tetoEncontrado.valor_teto || 1);
    const novoGasto = gastoAtual + (valorAdicional > 0 ? valorAdicional : 0);
    const novoPerc = (novoGasto / valorTeto) * 100;
    const restante = valorTeto - novoGasto;

    elTextoCat.textContent = `📊 Consumo em ${tetoEncontrado.categoria}: ${formatarMoedaBRL(novoGasto)} de ${formatarMoedaBRL(valorTeto)}`;
    elPercFuturo.textContent = `${novoPerc.toFixed(1)}%`;
    elBarraFill.style.width = `${Math.min(100, novoPerc)}%`;

    if (novoGasto > valorTeto) {
        elBarraFill.className = "progress-bar-fill fill-danger";
        elDetalhe.textContent = `🚨 Atenção: Este gasto fará o teto exceder em ${formatarMoedaBRL(Math.abs(restante))}!`;
    } else if (novoPerc >= 80) {
        elBarraFill.className = "progress-bar-fill fill-warning";
        elDetalhe.textContent = `⚠️ Alerta: Restarão apenas ${formatarMoedaBRL(restante)} disponíveis no teto.`;
    } else {
        elBarraFill.className = "progress-bar-fill fill-safe";
        elDetalhe.textContent = `✅ Dentro do orçamento: Saldo disponível no teto ficará em ${formatarMoedaBRL(restante)}.`;
    }
}

async function registrarGastoRapidoNoTeto(e) {
    e.preventDefault();
    const categoria = document.getElementById("rapido-categoria").value;
    const valorInput = document.getElementById("rapido-valor").value;
    const descricao = (document.getElementById("rapido-descricao").value || "").trim();
    const valor = parseFloat(String(valorInput).replace(",", "."));

    if (!descricao || isNaN(valor) || valor <= 0) {
        exibirAlertaBox("simulador-alert", "Informe a descrição e um valor maior que zero.", "error");
        return;
    }

    const btn = document.getElementById("btn-lancar-rapido");
    if (btn) {
        btn.disabled = true;
        btn.textContent = "Registrando...";
    }

    try {
        const res = await fetch("/api/transacoes", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                tipo: "despesa",
                categoria: categoria,
                valor: valor,
                descricao: descricao
            })
        });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            exibirAlertaBox("simulador-alert", `Gasto de ${formatarMoedaBRL(valor)} lançado em ${categoria}!`, "success");
            document.getElementById("form-gasto-rapido-teto").reset();
            document.getElementById("rapido-categoria").value = categoria;
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            await carregarTetosGastos();
        } else {
            exibirAlertaBox("simulador-alert", data.erro || "Erro ao registrar gasto.", "error");
        }
    } catch (err) {
        exibirAlertaBox("simulador-alert", "Erro de conexão com o servidor.", "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = "Registrar Gasto";
        }
    }
}

function renderizarCardsTetos(tetos) {
    const totalOrcado = tetos.reduce((acc, t) => acc + Number(t.valor_teto || 0), 0);
    const totalConsumido = tetos.reduce((acc, t) => acc + Number(t.gasto_atual || 0), 0);
    const margemDisponivel = Math.max(0, totalOrcado - totalConsumido);
    const percGlobal = totalOrcado > 0 ? ((totalConsumido / totalOrcado) * 100).toFixed(1) : 0;
    const qtdEstourados = tetos.filter((t) => t.estourou).length;

    document.getElementById("metric-total-tetos").textContent = formatarMoedaBRL(totalOrcado);
    document.getElementById("sub-qtd-tetos").textContent = `${tetos.length} limite(s) configurado(s)`;

    document.getElementById("metric-total-gasto-tetos").textContent = formatarMoedaBRL(totalConsumido);
    document.getElementById("sub-perc-geral").textContent = `${percGlobal}% do orçamento total consumido`;

    const elMargem = document.getElementById("metric-margem-disponivel");
    elMargem.textContent = formatarMoedaBRL(margemDisponivel);
    elMargem.className = `metric-value ${qtdEstourados > 0 ? "text-red" : "text-green"}`;

    const elStatusAlertas = document.getElementById("sub-status-alertas");
    if (tetos.length === 0) {
        elStatusAlertas.textContent = "Cadastre limites para monitorar seus gastos";
    } else if (qtdEstourados > 0) {
        elStatusAlertas.textContent = `🚨 Atenção: ${qtdEstourados} categoria(s) acima do teto!`;
    } else {
        elStatusAlertas.textContent = "✅ Todos os limites estão dentro do orçamento";
    }
}

function renderizarGraficoComparativoTetos(tetos) {
    const canvas = document.getElementById("chart-comparativo-tetos");
    const msgEmpty = document.getElementById("chart-tetos-empty");
    if (!canvas || typeof Chart === "undefined") return;

    if (!tetos || tetos.length === 0) {
        canvas.style.display = "none";
        if (msgEmpty) msgEmpty.style.display = "block";
        if (instanciaChartTetos) {
            instanciaChartTetos.destroy();
            instanciaChartTetos = null;
        }
        return;
    }

    canvas.style.display = "block";
    if (msgEmpty) msgEmpty.style.display = "none";

    const labels = tetos.map((t) => t.categoria);
    const valoresTeto = tetos.map((t) => Number(t.valor_teto || 0));
    const valoresGasto = tetos.map((t) => Number(t.gasto_atual || 0));
    const coresGasto = tetos.map((t) =>
        t.estourou ? "rgba(239, 68, 68, 0.88)" : (t.percentual >= 80 ? "rgba(245, 158, 11, 0.88)" : "rgba(16, 185, 129, 0.88)")
    );

    if (instanciaChartTetos) {
        instanciaChartTetos.data.labels = labels;
        instanciaChartTetos.data.datasets[0].data = valoresTeto;
        instanciaChartTetos.data.datasets[1].data = valoresGasto;
        instanciaChartTetos.data.datasets[1].backgroundColor = coresGasto;
        instanciaChartTetos.update();
        return;
    }

    const ctx = canvas.getContext("2d");
    instanciaChartTetos = new Chart(ctx, {
        type: "bar",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Teto Máximo (R$)",
                    data: valoresTeto,
                    backgroundColor: "rgba(59, 130, 246, 0.75)",
                    borderColor: "#3b82f6",
                    borderWidth: 1,
                    borderRadius: 6
                },
                {
                    label: "Gasto Realizado (R$)",
                    data: valoresGasto,
                    backgroundColor: coresGasto,
                    borderRadius: 6
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    ticks: { color: "#cbd5e1" },
                    grid: { color: "rgba(148, 163, 184, 0.08)" }
                },
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: "#94a3b8",
                        callback: (v) => "R$ " + Number(v).toLocaleString("pt-BR")
                    },
                    grid: { color: "rgba(148, 163, 184, 0.1)" }
                }
            },
            plugins: {
                legend: {
                    position: "top",
                    labels: { color: "#f8fafc" }
                },
                tooltip: {
                    callbacks: {
                        label: (ctx) => ` ${ctx.dataset.label}: ${formatarMoedaBRL(ctx.parsed.y)}`
                    }
                }
            }
        }
    });
}

function renderizarTabelaTetos(tetos) {
    const tbody = document.getElementById("tabela-tetos-body");
    if (!tbody) return;

    if (!tetos || tetos.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="empty-msg">
                    Nenhum teto de gastos cadastrado. Adicione acima ou envie no Assistente IA: <code>teto Alimentação 600</code>.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = tetos.map((t) => {
        const perc = Number(t.percentual || 0);
        const larguraBarra = Math.min(100, perc);

        let classeBarra = "fill-safe";
        let classeBadge = "status-ok";
        let textoBadge = `Disponível: ${formatarMoedaBRL(t.disponivel)}`;

        if (t.estourou) {
            classeBarra = "fill-danger";
            classeBadge = "status-danger";
            textoBadge = `Excedeu ${formatarMoedaBRL(t.gasto_atual - t.valor_teto)}`;
        } else if (perc >= 80) {
            classeBarra = "fill-warning";
            classeBadge = "status-warn";
            textoBadge = `Alerta (${perc.toFixed(0)}%)`;
        }

        const catSeguraAttr = String(t.categoria).replace(/"/g, "&quot;");

        return `
            <tr>
                <td><strong>${t.categoria}</strong></td>
                <td class="${t.estourou ? "text-red" : ""}" style="font-weight: 700;">
                    ${formatarMoedaBRL(t.gasto_atual)}
                </td>
                <td style="font-weight: 700; color: #60a5fa;">
                    ${formatarMoedaBRL(t.valor_teto)}
                </td>
                <td class="progress-cell">
                    <div class="progress-info">
                        <span>Consumo</span>
                        <strong>${perc.toFixed(1)}%</strong>
                    </div>
                    <div class="progress-track">
                        <div class="progress-bar-fill ${classeBarra}" style="width: ${larguraBarra}%;"></div>
                    </div>
                </td>
                <td>
                    <span class="badge-status-teto ${classeBadge}">${textoBadge}</span>
                </td>
                <td style="text-align: right;">
                    <div class="teto-actions">
                        <button type="button" class="btn-action-edit"
                            data-categoria="${catSeguraAttr}"
                            data-valor="${Number(t.valor_teto)}">
                            ✏️ Editar
                        </button>
                        <button type="button" class="btn-action-del"
                            data-categoria="${catSeguraAttr}">
                            🗑️ Excluir
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

async function salvarTetoGasto(e) {
    e.preventDefault();
    const tipoAlvo = document.getElementById("select-tipo-alvo").value;
    const catSelect = document.getElementById("input-categoria-teto").value;
    const itemCustom = (document.getElementById("input-item-especifico").value || "").trim();
    const valorInput = document.getElementById("input-valor-teto").value;

    const categoriaFinal = tipoAlvo === "item" ? itemCustom : catSelect;
    const valor_teto = parseFloat(String(valorInput).replace(",", "."));

    if (!categoriaFinal) {
        exibirAlertaTeto("Informe o nome da categoria ou item específico.", "error");
        return;
    }
    if (isNaN(valor_teto) || valor_teto <= 0) {
        exibirAlertaTeto("O valor do teto deve ser maior que zero.", "error");
        return;
    }

    try {
        const res = await fetch("/api/tetos", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({ categoria: categoriaFinal, valor_teto })
        });
        const data = await res.json();

        if (res.ok && data.sucesso) {
            exibirAlertaTeto(`Teto de ${categoriaFinal} salvo em ${formatarMoedaBRL(valor_teto)}!`, "success");
            resetarFormularioTeto();
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            await carregarTetosGastos();
        } else {
            exibirAlertaTeto(data.erro || "Erro ao salvar teto de gastos.", "error");
        }
    } catch (err) {
        exibirAlertaTeto("Erro de conexão com o servidor.", "error");
    }
}

function prepararEdicaoTeto(categoria, valorAtual) {
    if (!categoria) return;

    const categoriaPadraoEncontrada = CATEGORIAS_PADRAO.find(
        (c) => c.toLowerCase() === String(categoria).toLowerCase()
    );

    const selectTipo = document.getElementById("select-tipo-alvo");
    if (categoriaPadraoEncontrada) {
        selectTipo.value = "categoria";
        alternarCampoAlvo();
        document.getElementById("input-categoria-teto").value = categoriaPadraoEncontrada;
    } else {
        selectTipo.value = "item";
        alternarCampoAlvo();
        document.getElementById("input-item-especifico").value = categoria;
    }

    const inputValor = document.getElementById("input-valor-teto");
    inputValor.value = Number(valorAtual || 0).toFixed(2);

    document.getElementById("titulo-form-teto").textContent = `✏️ Editar Teto: ${categoria}`;
    document.getElementById("btn-salvar-teto").textContent = "Atualizar Teto";
    document.getElementById("btn-cancelar-edicao").style.display = "inline-block";

    inputValor.scrollIntoView({ behavior: "smooth", block: "center" });
    inputValor.focus();
    inputValor.select();
}

function resetarFormularioTeto() {
    document.getElementById("form-teto-gasto").reset();
    document.getElementById("select-tipo-alvo").value = "categoria";
    alternarCampoAlvo();
    document.getElementById("titulo-form-teto").textContent = "➕ Definir Teto de Gastos";
    document.getElementById("btn-salvar-teto").textContent = "Salvar Teto";
    document.getElementById("btn-cancelar-edicao").style.display = "none";
}

async function excluirTeto(categoria) {
    if (!categoria) return;

    try {
        const res = await fetch(`/api/tetos/${encodeURIComponent(categoria)}`, {
            method: "DELETE",
            credentials: "same-origin"
        });
        const data = await res.json().catch(() => ({}));

        if (res.ok && data.sucesso !== false) {
            exibirAlertaTeto(`Teto de '${categoria}' removido com sucesso.`, "success");
            resetarFormularioTeto();
            localStorage.setItem("ultima_atualizacao_financeira", Date.now().toString());
            await carregarTetosGastos();
        } else {
            exibirAlertaTeto(data.erro || "Não foi possível excluir o teto.", "error");
        }
    } catch (err) {
        exibirAlertaTeto("Erro ao excluir teto de gastos.", "error");
    }
}

window.prepararEdicaoTeto = prepararEdicaoTeto;
window.excluirTeto = excluirTeto;