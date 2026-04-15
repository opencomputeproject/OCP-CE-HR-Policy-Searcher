import './App.css';
import AgentPanel from './components/AgentPanel';
import TempLogoImage from './assets/templogo.png';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>OCP Policy Searcher</h1>
        <AgentPanel />
        <img src={TempLogoImage} alt="Temp Logo" className="logo-image" />
      </header>
    </div>
  );
}

export default App;
