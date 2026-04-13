import logo from './logo.svg';
import './App.css';
import PolicyList from './components/PolicyList';
import TempLogoImage from './assets/templogo.png';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>OCP Policy Searcher</h1>
        <PolicyList />
        <img src={TempLogoImage} alt="Temp Logo" style={{ width: '200px' }} />
      </header>
    </div>
  );
}

export default App;
