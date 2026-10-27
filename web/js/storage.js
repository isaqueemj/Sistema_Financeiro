// storage.js
// Arquivo central para manipulação dos dados do FinanceControl usando localStorage

const StorageFinance = {
  // Chaves usadas no localStorage
  keys: {
    userName: "finance_user_name",
    receitas: "finance_receitas",
    despesas: "finance_despesas",
    theme: "finance_theme"
  },

  // =========================
  // USUÁRIO
  // =========================

  getUserName() {
    return localStorage.getItem(this.keys.userName) || "Usuário";
  },

  setUserName(name) {
    localStorage.setItem(this.keys.userName, name);
  },

  clearSession() {
    localStorage.removeItem(this.keys.userName);
  },

  // =========================
  // TEMA
  // =========================

  getTheme() {
    return localStorage.getItem(this.keys.theme) || "light";
  },

  setTheme(theme) {
    localStorage.setItem(this.keys.theme, theme);
  },

  applyTheme() {
    const theme = this.getTheme();

    if (theme === "dark") {
      document.body.classList.add("dark-mode");
    } else {
      document.body.classList.remove("dark-mode");
    }
  },

  // =========================
  // RECEITAS
  // =========================

  getReceitas() {
    return JSON.parse(localStorage.getItem(this.keys.receitas)) || [];
  },

  saveReceitas(receitas) {
    localStorage.setItem(this.keys.receitas, JSON.stringify(receitas));
  },

  addReceita(receita) {
    const receitas = this.getReceitas();
    receitas.push(receita);
    this.saveReceitas(receitas);
  },

  updateReceita(id, updatedReceita) {
    const receitas = this.getReceitas().map(receita => {
      return receita.id === id ? updatedReceita : receita;
    });

    this.saveReceitas(receitas);
  },

  deleteReceita(id) {
    const receitas = this.getReceitas().filter(receita => receita.id !== id);
    this.saveReceitas(receitas);
  },

  // =========================
  // DESPESAS
  // =========================

  getDespesas() {
    return JSON.parse(localStorage.getItem(this.keys.despesas)) || [];
  },

  saveDespesas(despesas) {
    localStorage.setItem(this.keys.despesas, JSON.stringify(despesas));
  },

  addDespesa(despesa) {
    const despesas = this.getDespesas();
    despesas.push(despesa);
    this.saveDespesas(despesas);
  },

  updateDespesa(id, updatedDespesa) {
    const despesas = this.getDespesas().map(despesa => {
      return despesa.id === id ? updatedDespesa : despesa;
    });

    this.saveDespesas(despesas);
  },

  deleteDespesa(id) {
    const despesas = this.getDespesas().filter(despesa => despesa.id !== id);
    this.saveDespesas(despesas);
  },

  // =========================
  // CÁLCULOS FINANCEIROS
  // =========================

  getTotalReceitas() {
    return this.getReceitas().reduce((total, receita) => {
      return total + Number(receita.valor);
    }, 0);
  },

  getTotalDespesas() {
    return this.getDespesas().reduce((total, despesa) => {
      return total + Number(despesa.valor);
    }, 0);
  },

  getSaldoAtual() {
    return this.getTotalReceitas() - this.getTotalDespesas();
  },

  getAllTransactions() {
    const receitas = this.getReceitas().map(item => ({
      ...item,
      tipo: "Receita"
    }));

    const despesas = this.getDespesas().map(item => ({
      ...item,
      tipo: "Despesa"
    }));

    return [...receitas, ...despesas].sort((a, b) => {
      return new Date(b.data) - new Date(a.data);
    });
  },

  formatCurrency(value) {
    return Number(value).toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL"
    });
  },

  formatDate(date) {
    if (!date) return "-";

    const dateObj = new Date(date + "T00:00:00");

    return dateObj.toLocaleDateString("pt-BR");
  }
};

// Função global para preencher o nome do usuário no topo das páginas
function loadUserNameOnHeader() {
  const userNameElement = document.getElementById("loggedUserName");

  if (userNameElement) {
    userNameElement.textContent = `Olá, ${StorageFinance.getUserName()}`;
  }
}

// Função global para destacar link ativo do menu
function setActiveMenu() {
  const currentPage = window.location.pathname.split("/").pop();
  const menuLinks = document.querySelectorAll(".sidebar a");

  menuLinks.forEach(link => {
    const href = link.getAttribute("href");

    if (href === currentPage) {
      link.classList.add("active");
    }
  });
}

// Executa funções comuns em todas as páginas
document.addEventListener("DOMContentLoaded", function () {
  StorageFinance.applyTheme();
  loadUserNameOnHeader();
  setActiveMenu();
});
``