// relatorios.js
// Lógica para carregar relatórios, renderizar gráficos Dark Mode e exportar PDF de GASTOS

document.addEventListener("DOMContentLoaded", function () {
    carregarNomeDoBanco();
    carregarRelatorios();
    
    // Listener para o botão de PDF
    const btnPDF = document.getElementById("btnGerarPDF");
    if (btnPDF) {
        btnPDF.addEventListener("click", gerarPDF);
    }
});

let graficoPizza = null;
let graficoBarra = null;
let graficoCategoria = null;

// Configuração de Cores para o Tema Escuro
const chartColors = {
    text: '#94a3b8',
    grid: '#334155',
    green: '#10b981',
    red: '#ef4444',
    blue: '#3b82f6',
    blueHover: '#60a5fa'
};

// Configuração Global do Chart.js para Dark Mode
Chart.defaults.color = chartColors.text;
Chart.defaults.borderColor = chartColors.grid;

async function carregarRelatorios() {
    try {
        const response = await fetch('/api/transacoes');
        if (!response.ok) throw new Error("Erro ao buscar dados do servidor.");

        const transacoes = await response.json();

        let totalReceitas = 0;
        let totalDespesas = 0;
        let maiorReceita = 0;
        let maiorDespesa = 0;
        
        let despesasPorCategoria = {};
        let receitasPorMes = {};
        let despesasPorMes = {};

        const formatarMoeda = (valor) => new Intl.NumberFormat('pt-BR', { 
            style: 'currency', 
            currency: 'BRL' 
        }).format(valor);

        const tbody = document.getElementById('statementTableBody');
        if (!tbody) return;
        
        let linhasTabela = '';

        transacoes.forEach(t => {
            const valor = Number(t.valor);
            const tipo = t.tipo.toLowerCase();
            const categoria = t.categoria || "Outros";
            
            // Tratamento de Data para os gráficos (YYYY-MM)
            const mesAno = t.data ? t.data.substring(0, 7) : "Indefinido";
            
            // Tratamento corrigido de Data e Hora para a Tabela (DD/MM/YYYY às HH:MM)
            const dataFormatadaParaTabela = formatarDataHora(t.data);

            if (tipo === 'receita') {
                totalReceitas += valor;
                if (valor > maiorReceita) maiorReceita = valor;
                receitasPorMes[mesAno] = (receitasPorMes[mesAno] || 0) + valor;
                
                linhasTabela += criarLinhaTabela(dataFormatadaParaTabela, t.descricao, categoria, 'Receita', valor, formatarMoeda);
            } else if (tipo === 'despesa') {
                totalDespesas += valor;
                if (valor > maiorDespesa) maiorDespesa = valor;
                despesasPorCategoria[categoria] = (despesasPorCategoria[categoria] || 0) + valor;
                despesasPorMes[mesAno] = (despesasPorMes[mesAno] || 0) + valor;
                
                linhasTabela += criarLinhaTabela(dataFormatadaParaTabela, t.descricao, categoria, 'Despesa', valor, formatarMoeda);
            }
        });

        tbody.innerHTML = linhasTabela || `<tr><td colspan="5" style="text-align: center;">Nenhuma movimentação registrada.</td></tr>`;

        // Cálculos Finais
        const saldoAtual = totalReceitas - totalDespesas;
        const totalTransacoesDespesa = Object.values(despesasPorCategoria).length > 0 ? 
              transacoes.filter(t => t.tipo.toLowerCase() === 'despesa').length : 1; 
        const mediaGastos = totalDespesas / (totalTransacoesDespesa || 1);

        // Atualiza os Textos no DOM
        const elReceitas = document.getElementById("reportReceitas");
        const elDespesas = document.getElementById("reportDespesas");
        if (elReceitas) elReceitas.textContent = formatarMoeda(totalReceitas);
        if (elDespesas) elDespesas.textContent = formatarMoeda(totalDespesas);
        
        const elSaldo = document.getElementById("reportSaldo");
        if (elSaldo) elSaldo.textContent = formatarMoeda(saldoAtual);
        
        // Atualiza Métricas Extras
        const elMaiorRec = document.getElementById("maiorReceita");
        const elMaiorDesp = document.getElementById("maiorDespesa");
        const elMediaGastos = document.getElementById("mediaGastos");

        if (elMaiorRec) elMaiorRec.textContent = formatarMoeda(maiorReceita);
        if (elMaiorDesp) elMaiorDesp.textContent = formatarMoeda(maiorDespesa);
        if (elMediaGastos) elMediaGastos.textContent = formatarMoeda(mediaGastos);

        // Renderiza Gráficos
        renderizarGraficoPizza(totalReceitas, totalDespesas);
        renderizarGraficoBarra(receitasPorMes, despesasPorMes);
        renderizarGraficoCategoria(despesasPorCategoria);

    } catch (error) {
        console.error("Erro ao carregar relatórios:", error);
    }
}

function criarLinhaTabela(data, desc, cat, tipo, valor, formatador) {
    const isReceita = tipo === 'Receita';
    const badgeClass = isReceita ? 'badge income' : 'badge expense';
    const valorCor = isReceita ? 'text-green' : 'text-red';
    const rowClass = isReceita ? 'linha-receita' : 'linha-despesa'; 
    
    return `
        <tr class="${rowClass}">
            <td>${data}</td>
            <td><strong>${desc}</strong></td>
            <td>${cat}</td>
            <td><span class="${badgeClass}">${tipo}</span></td>
            <td class="align-right ${valorCor}"><strong>${formatador(valor)}</strong></td>
        </tr>
    `;
}

function formatarDataHora(dataString) {
    if (!dataString) return "-";
    
    // Divide a data e a hora salvas no banco (ex: "2026-09-02 14:35:10")
    const partes = dataString.split(/[\sT]/);
    const dataPart = partes[0]; // "2026-09-02"
    let horaPart = partes[1] ? partes[1].substring(0, 5) : ""; // "14:35"

    // Organiza a data de YYYY-MM-DD para DD/MM/YYYY
    const dArray = dataPart.split('-');
    const dataFormatada = dArray.length === 3 ? `${dArray[2]}/${dArray[1]}/${dArray[0]}` : dataPart;

    // Retorna exatamente o horário fixo que foi gravado no banco
    return horaPart ? `${dataFormatada} às ${horaPart}` : dataFormatada;
}

async function carregarNomeDoBanco() {
    const usuarioLogado = localStorage.getItem("financeControl_user");
    const spanNome = document.getElementById("loggedUserName");

    if (!spanNome) return;

    if (usuarioLogado) {
        try {
            const response = await fetch(`/api/usuario/${usuarioLogado}`);
            if (response.ok) {
                const dados = await response.json();
                spanNome.textContent = `Olá, ${dados.nome}`;
                localStorage.setItem("financeControl_userName", dados.nome);
                return;
            }
        } catch (error) {
            console.error("Erro ao buscar nome do banco:", error);
        }
    }

    const nomeSalvo = localStorage.getItem("financeControl_userName") || "Usuário";
    spanNome.textContent = `Olá, ${nomeSalvo}`;
}

function renderizarGraficoPizza(receitas, despesas) {
    const canvas = document.getElementById('pizzaChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (graficoPizza) graficoPizza.destroy();

    graficoPizza = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Receitas', 'Despesas'],
            datasets: [{
                data: [receitas, despesas],
                backgroundColor: [chartColors.green, chartColors.red],
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: { legend: { position: 'bottom', labels: { padding: 20 } } }
        }
    });
}

function renderizarGraficoBarra(receitasMes, despesasMes) {
    const canvas = document.getElementById('barChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (graficoBarra) graficoBarra.destroy();

    const mesesUnicos = [...new Set([...Object.keys(receitasMes), ...Object.keys(despesasMes)])].sort();
    const dadosReceitas = mesesUnicos.map(m => receitasMes[m] || 0);
    const dadosDespesas = mesesUnicos.map(m => despesasMes[m] || 0);

    const labelsFormatados = mesesUnicos.map(m => {
        const partes = m.split('-');
        return partes.length === 2 ? `${partes[1]}/${partes[0]}` : m;
    });

    graficoBarra = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labelsFormatados,
            datasets: [
                { label: 'Receitas', data: dadosReceitas, backgroundColor: chartColors.green, borderRadius: 4 },
                { label: 'Despesas', data: dadosDespesas, backgroundColor: chartColors.red, borderRadius: 4 }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: chartColors.grid } },
                x: { grid: { display: false } }
            },
            plugins: { legend: { position: 'top' } }
        }
    });
}

function renderizarGraficoCategoria(categoriasObj) {
    const canvas = document.getElementById('categoryChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (graficoCategoria) graficoCategoria.destroy();

    const categoriasOrdenadas = Object.entries(categoriasObj).sort((a, b) => b[1] - a[1]);
    const categorias = categoriasOrdenadas.map(c => c[0]);
    const valores = categoriasOrdenadas.map(c => c[1]);

    graficoCategoria = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: categorias.length > 0 ? categorias : ['Nenhuma despesa'],
            datasets: [{
                label: 'Gastos por Categoria (R$)',
                data: valores.length > 0 ? valores : [0],
                backgroundColor: chartColors.blue,
                hoverBackgroundColor: chartColors.blueHover,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { beginAtZero: true, grid: { color: chartColors.grid } },
                x: { grid: { display: false } }
            },
            plugins: { legend: { display: false } }
        }
    });
}

function gerarPDF() {
    const elementoRelatorio = document.getElementById('areaRelatorioPDF');
    if (!elementoRelatorio) return;
    
    const dataEmissao = new Date().toLocaleDateString('pt-BR');
    const pdfHeader = document.querySelector('.pdf-header');
    
    if (pdfHeader) {
        pdfHeader.innerHTML = `
            <h2 style="color: white; margin-bottom: 5px;">Relatório de Despesas</h2>
            <p style="color: #94a3b8; font-size: 14px;">Data de emissão: ${dataEmissao}</p>
        `;
        pdfHeader.style.display = 'block';
    }

    const linhasReceita = document.querySelectorAll('.linha-receita');
    linhasReceita.forEach(linha => linha.style.display = 'none');

    const cardReceita = document.querySelector('.card.income');
    const cardSaldo = document.querySelector('.card.balance');
    const maiorRecEl = document.getElementById('maiorReceita');
    const metricMaiorReceita = maiorRecEl ? maiorRecEl.parentElement : null;
    
    if (cardReceita) cardReceita.style.display = 'none';
    if (cardSaldo) cardSaldo.style.display = 'none';
    if (metricMaiorReceita) metricMaiorReceita.style.display = 'none';

    const opt = {
        margin:       10,
        filename:     `Relatorio_Despesas_${dataEmissao.replace(/\//g, '-')}.pdf`,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  { scale: 2, useCORS: true, backgroundColor: '#0f172a' },
        jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' }
    };

    const btn = document.getElementById('btnGerarPDF');
    const textoOriginal = btn ? btn.innerText : '';
    if (btn) {
        btn.innerText = "⏳ Gerando...";
        btn.disabled = true;
    }

    html2pdf().set(opt).from(elementoRelatorio).save().then(() => {
        if (pdfHeader) pdfHeader.style.display = 'none';
        linhasReceita.forEach(linha => linha.style.display = '');
        if (cardReceita) cardReceita.style.display = 'flex';
        if (cardSaldo) cardSaldo.style.display = 'flex';
        if (metricMaiorReceita) metricMaiorReceita.style.display = 'flex';

        if (btn) {
            btn.innerText = textoOriginal;
            btn.disabled = false;
        }
    }).catch(err => {
        console.error("Erro ao gerar PDF:", err);
        alert("Houve um erro ao gerar o PDF.");
        
        if (pdfHeader) pdfHeader.style.display = 'none';
        linhasReceita.forEach(linha => linha.style.display = '');
        if (cardReceita) cardReceita.style.display = 'flex';
        if (cardSaldo) cardSaldo.style.display = 'flex';
        if (metricMaiorReceita) metricMaiorReceita.style.display = 'flex';

        if (btn) {
            btn.innerText = textoOriginal;
            btn.disabled = false;
        }
    });
}