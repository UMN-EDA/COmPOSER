#ifndef UTIL_H_
#define UTIL_H_
#include <chrono>
#include <iostream>
#include <string>
#include <fstream>

#define COUT std::cout //<< __FUNCTION__ << " -:- "
#define CERR std::cerr //<< __FUNCTION__ << " -:- "

class TimeMeasure {
  private:
    const std::string _name;
    std::chrono::nanoseconds* _rt;
    std::chrono::high_resolution_clock::time_point _begin;
  public:
    TimeMeasure(const std::string& name, std::chrono::nanoseconds* rt = nullptr) : _name(name), _rt(rt)
    {
      _begin = std::chrono::high_resolution_clock::now();
    }
    ~TimeMeasure()
    {
      auto difft = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::high_resolution_clock::now() - _begin);
      if (_rt) {
        (*_rt) += difft;
      } else {
        std::cout << _name << " runtime : " << difft.count()/1.e9 << "(s)\n";
      }
    }
};
#define TIME_MA(X) TimeMeasure __FUNC__##t(__PRETTY_FUNCTION__, X)
#define TIME_M()  TimeMeasure __FUNC__##t(__PRETTY_FUNCTION__)

class SaveRestoreStream {
  private:
    std::ofstream _ofs, _efs;
    std::streambuf *_ostream, *_estream;
  public:
    SaveRestoreStream(const std::string& logname, const std::string& errname = "err.log") : _ofs(logname), _efs(errname),
    _ostream(std::cout.rdbuf()), _estream(std::cerr.rdbuf())
    {
      if (_ofs) {
        std::cout.rdbuf(_ofs.rdbuf());
      } else {
        _ofs.close();
      }
      if (_efs) {
        std::cerr.rdbuf(_efs.rdbuf());
      } else {
        _efs.close();
      }
    }
    ~SaveRestoreStream()
    {
      if (_ofs) {
        std::cout.rdbuf(_ostream);
      }
      if (_efs) {
        std::cerr.rdbuf(_estream);
      }
    }
};

#endif
