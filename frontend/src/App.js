import logo from './logo.svg';
import './App.css';
import PolicyList from './components/PolicyList';

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>OCP Policy Searcher</h1>
        <PolicyList />
      </header>
    </div>
  );
}

export default App;
