"""Encrypted at rest; master key is outside the state database."""
import os
from pathlib import Path
from cryptography.fernet import Fernet

class Vault:
    def __init__(self,store):
        self.store=store
        key=os.getenv('INET_MASTER_KEY')
        if not key:
            path=Path(os.getenv('RUNTIME_DB','runtime/state.sqlite3')).parent/'master.key'
            path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as stream: stream.write(Fernet.generate_key())
            key=path.read_bytes()
        self.cipher=Fernet(key)

    def set(self,name,value):
        self.store.save('secrets',name,{'ciphertext':self.cipher.encrypt(value.encode()).decode()})

    def get(self,name):
        record=self.store.load('secrets',name)
        return self.cipher.decrypt(record['ciphertext'].encode()).decode() if record else os.getenv(name.upper()+'_API_KEY','')

    def configured(self,name): return bool(self.store.load('secrets',name) or os.getenv(name.upper()+'_API_KEY'))
